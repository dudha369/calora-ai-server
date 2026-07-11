"""
Backblaze B2 через S3-совместимый API (boto3).

Клиент создаётся один раз (singleton) и переиспользуется.

Важно: B2 по умолчанию хранит все версии файлов. Обычный delete_object
без VersionId создаёт «hide marker» (0 bytes, помечен hidden) вместо
физического удаления. Для настоящего удаления нужно:
  1. list_object_versions → получить все VersionId (включая маркеры)
  2. delete_objects с явными VersionId
"""

import asyncio
import uuid
from io import BytesIO
import logging
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from config import config

logger = logging.getLogger(__name__)

PRESIGNED_URL_TTL = 60 * 60 * 24  # 24 часа

# ─── Singleton B2 client ─────────────────────────────────────────────────────

_b2_client = None


def _is_configured() -> bool:
    return bool(
        config.B2_ENDPOINT
        and config.B2_KEY_ID.get_secret_value()
        and config.B2_APPLICATION_KEY.get_secret_value()
        and config.B2_BUCKET
    )


def _get_client():
    """Возвращает singleton boto3 S3 client. Создаёт при первом вызове."""
    global _b2_client
    if _b2_client is None:
        _b2_client = boto3.client(
            service_name="s3",
            endpoint_url=config.B2_ENDPOINT,
            aws_access_key_id=config.B2_KEY_ID.get_secret_value(),
            aws_secret_access_key=config.B2_APPLICATION_KEY.get_secret_value(),
            config=BotoConfig(signature_version="s3v4"),
        )
    return _b2_client


# ─── Version-aware helper ────────────────────────────────────────────────────


def _collect_all_versions(client, object_key: str) -> list[dict]:
    """
    Возвращает список всех версий и delete-маркеров для данного ключа.

    B2 с «Keep all versions» хранит историю:
    - Versions      — реальные версии файла
    - DeleteMarkers — 0-byte маркеры, созданные delete_object без VersionId

    Фильтруем по ТОЧНОМУ совпадению ключа: Prefix — это prefix-match,
    поэтому "food/1/abc.jpg" мог бы захватить "food/1/abc.jpg.bak".

    Возвращает [] если версионирование не поддерживается или файл не существует.
    Caller должен сделать fallback на простой delete_object.
    """
    try:
        response = client.list_object_versions(
            Bucket=config.B2_BUCKET,
            Prefix=object_key,
        )
        all_entries = response.get("Versions", []) + response.get("DeleteMarkers", [])
        return [
            {"Key": v["Key"], "VersionId": v["VersionId"]}
            for v in all_entries
            if v["Key"] == object_key and v.get("VersionId")
        ]
    except (BotoCoreError, ClientError) as e:
        # NotImplemented = бакет без версионирования → возвращаем [] → caller
        # использует простой delete_object. Остальные ошибки — тоже fallback.
        logger.debug("list_object_versions unavailable for %s: %s", object_key, e)
        return []


# ─── Sync operations (run via asyncio.to_thread) ─────────────────────────────


def _sync_upload(image_bytes: bytes, object_key: str, mime_type: str) -> None:
    """Синхронная загрузка — выполняется в потоке через asyncio.to_thread."""
    client = _get_client()
    client.upload_fileobj(
        BytesIO(image_bytes),
        config.B2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": mime_type},
    )


def _sync_presign(object_key: str) -> str:
    """Генерирует временную ссылку для приватного объекта."""
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": config.B2_BUCKET, "Key": object_key},
        ExpiresIn=PRESIGNED_URL_TTL,
    )


def _sync_delete(object_key: str) -> None:
    """
    Permanently deletes an object — все версии и hide-маркеры.

    Проблема с обычным delete_object:
      B2 при delete_object без VersionId создаёт hide-marker (0-byte файл
      с пометкой «hidden»). Реальный файл остаётся, занимает место, виден
      в консоли как «filename.jpg (hidden)». Именно это было на скриншоте.

    Решение:
      1. list_object_versions → все VersionId (файлы + маркеры)
      2. delete_objects с явными VersionId → физическое удаление
      3. Если версий нет → fallback delete_object (не-версионированный бакет)
    """
    client = _get_client()
    versions = _collect_all_versions(client, object_key)

    if versions:
        client.delete_objects(
            Bucket=config.B2_BUCKET,
            Delete={"Objects": versions, "Quiet": True},
        )
    else:
        # Fallback: не-версионированный бакет или файл не существует.
        # delete_object на несуществующий ключ в S3/B2 возвращает 204 — безопасно.
        client.delete_object(Bucket=config.B2_BUCKET, Key=object_key)


def _sync_delete_many(object_keys: list[str]) -> None:
    """
    Batch permanent deletion — все версии для каждого ключа.

    Стратегия: собрать все VersionId для всех ключей, затем удалить одним
    batch'ем (или несколькими, если > 1000). Ключи без версий добавляются
    без VersionId — корректно для не-версионированных бакетов.
    """
    client = _get_client()
    to_delete: list[dict] = []

    for key in object_keys:
        versions = _collect_all_versions(client, key)
        if versions:
            to_delete.extend(versions)
        else:
            to_delete.append({"Key": key})

    # S3/B2: max 1000 объектов за один delete_objects запрос
    for i in range(0, len(to_delete), 1000):
        client.delete_objects(
            Bucket=config.B2_BUCKET,
            Delete={"Objects": to_delete[i : i + 1000], "Quiet": True},
        )


# ─── Async public API ─────────────────────────────────────────────────────────


async def upload_food_photo(
    image_bytes: bytes,
    user_id: int,
    mime_type: str = "image/jpeg",
) -> Optional[str]:
    """
    Загружает фото в B2 и возвращает КЛЮЧ объекта (не URL!).
    Ключ сохраняем в БД. Для отображения — вызывай get_photo_url(key).

    Возвращает None если B2 не настроен или ошибка загрузки.
    """
    if not _is_configured():
        return None

    ext = "jpg" if "jpeg" in mime_type else mime_type.split("/")[-1]
    object_key = f"food/{user_id}/{uuid.uuid4().hex}.{ext}"

    try:
        await asyncio.to_thread(_sync_upload, image_bytes, object_key, mime_type)
        return object_key
    except (BotoCoreError, ClientError) as e:
        logger.error("B2 upload failed for user %s: %s", user_id, e)
        return None


async def get_photo_url(object_key: Optional[str]) -> Optional[str]:
    """
    По ключу из БД генерирует presigned URL действительный 24 часа.
    Если это уже готовый внешний URL (например, картинка с OpenFoodFacts) —
    возвращаем как есть, без похода в B2.
    """
    if not object_key:
        return None
    if object_key.startswith("http://") or object_key.startswith("https://"):
        return object_key
    if not _is_configured():
        return None
    try:
        return await asyncio.to_thread(_sync_presign, object_key)
    except (BotoCoreError, ClientError) as e:
        logger.error("B2 presign failed for key %s: %s", object_key, e)
        return None


async def delete_food_photo(object_key: Optional[str]) -> None:
    """Удаляет одно фото — все версии и hide-маркеры.
    Внешние URL (например с OpenFoodFacts) в B2 не лежат — их не трогаем."""
    if not object_key or not _is_configured():
        return
    if object_key.startswith("http://") or object_key.startswith("https://"):
        return
    try:
        await asyncio.to_thread(_sync_delete, object_key)
    except (BotoCoreError, ClientError) as e:
        logger.error("B2 delete failed for key %s: %s", object_key, e)


async def delete_food_photos(object_keys: list[str]) -> None:
    """Батч-удаление всех фото пользователя (при удалении аккаунта)."""
    keys = [
        k for k in object_keys
        if k and not k.startswith("http://") and not k.startswith("https://")
    ]
    if not keys or not _is_configured():
        return
    try:
        await asyncio.to_thread(_sync_delete_many, keys)
    except (BotoCoreError, ClientError) as e:
        logger.error("B2 batch delete failed (%s keys): %s", len(keys), e)
