"""
Backblaze B2 через S3-совместимый API (boto3).
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

PRESIGNED_URL_TTL = 60 * 60 * 24


def _is_configured() -> bool:
    return bool(
        config.B2_ENDPOINT
        and config.B2_KEY_ID.get_secret_value()
        and config.B2_APPLICATION_KEY.get_secret_value()
        and config.B2_BUCKET
    )


def _make_client():
    return boto3.client(
        service_name="s3",
        endpoint_url=config.B2_ENDPOINT,
        aws_access_key_id=config.B2_KEY_ID.get_secret_value(),
        aws_secret_access_key=config.B2_APPLICATION_KEY.get_secret_value(),
        config=BotoConfig(signature_version="s3v4"),
    )


def _sync_upload(image_bytes: bytes, object_key: str, mime_type: str) -> None:
    """Синхронная загрузка — выполняется в потоке через asyncio.to_thread."""
    client = _make_client()
    client.upload_fileobj(
        BytesIO(image_bytes),
        config.B2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": mime_type},
        # ACL не указываем — бакет приватный, файл тоже приватный
    )


def _sync_presign(object_key: str) -> str:
    """Генерирует временную ссылку для приватного объекта."""
    client = _make_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": config.B2_BUCKET, "Key": object_key},
        ExpiresIn=PRESIGNED_URL_TTL,
    )


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
        logger.error(f"B2 upload failed for user {user_id}: {e}")
        return None


async def get_photo_url(object_key: Optional[str]) -> Optional[str]:
    """
    По ключу из БД генерирует presigned URL действительный 24 часа.
    Используй в src тега <img> — работает как обычная ссылка.

    Если ключ None или B2 не настроен — возвращает None.
    """
    if not object_key or not _is_configured():
        return None
    try:
        return await asyncio.to_thread(_sync_presign, object_key)
    except (BotoCoreError, ClientError) as e:
        logger.error(f"B2 presign failed for key {object_key}: {e}")
        return None
