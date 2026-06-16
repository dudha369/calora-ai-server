"""
Общие утилиты API: авторизация, работа с пользователем, валидация.

get_current_user — единственная точка входа для эндпоинтов.
Заменяет пару Depends(auth) + get_or_create_user() одним вызовом.
"""

import logging
import time
from collections import defaultdict
from datetime import date as date_type, datetime, timezone
from typing import Optional

from fastapi import Request, HTTPException, Depends
from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data

from config import config
from db import User

logger = logging.getLogger(__name__)


# ─── Rate Limiting ───────────────────────────────────────────────────────────

# {user_id: [timestamp, ...]}
_rate_limits: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
_last_cleanup: float = time.monotonic()
_CLEANUP_INTERVAL = 300  # 5 минут


def _cleanup_stale_entries() -> None:
    """Удаляет записи пользователей без активности за последние 5 минут."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now

    for bucket_key in list(_rate_limits.keys()):
        bucket = _rate_limits[bucket_key]
        for uid in list(bucket.keys()):
            bucket[uid] = [ts for ts in bucket[uid] if ts > now - 60]
            if not bucket[uid]:
                del bucket[uid]
        if not bucket:
            del _rate_limits[bucket_key]


def check_rate_limit(
    user_id: int,
    bucket: str = "default",
    max_per_minute: int = 5,
) -> None:
    """
    Проверяет rate limit: max_per_minute запросов в минуту на юзера.
    Разные bucket'ы для разных эндпоинтов.
    """
    _cleanup_stale_entries()

    now = time.monotonic()
    window = now - 60
    timestamps = _rate_limits[bucket][user_id]
    _rate_limits[bucket][user_id] = [ts for ts in timestamps if ts > window]
    if len(_rate_limits[bucket][user_id]) >= max_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Max {max_per_minute} per minute.",
        )
    _rate_limits[bucket][user_id].append(now)


# ─── Date Validation ─────────────────────────────────────────────────────────


def parse_date(value: str) -> date_type:
    """
    Парсит строку YYYY-MM-DD в date. Бросает HTTP 422 при невалидном формате.
    Используй вместо голого date.fromisoformat() в эндпоинтах.
    """
    try:
        return date_type.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format: '{value}'. Expected YYYY-MM-DD.",
        )


# ─── Auth ─────────────────────────────────────────────────────────────────────


def auth(request: Request) -> WebAppInitData:
    """
    Парсит и валидирует Telegram initData из заголовка.
    Возвращает WebAppInitData или бросает 401/403.
    """
    if request.method == "OPTIONS":
        # CORS preflight обрабатывается CORSMiddleware до вызова зависимостей,
        # но на случай прямого OPTIONS-запроса — явно отклоняем.
        raise HTTPException(status_code=400, detail="OPTIONS not supported here")

    try:
        auth_string = request.headers.get("initData")
        if not auth_string:
            raise HTTPException(status_code=401, detail={"error": "Unauthorized"})

        init_data = safe_parse_webapp_init_data(
            config.BOT_TOKEN.get_secret_value(), auth_string
        )

        if config.WHITELIST_ENABLED and init_data.user:
            if init_data.user.id not in config.whitelist_ids:
                raise HTTPException(
                    status_code=403,
                    detail={"error": "Access denied", "reason": "not_whitelisted"},
                )

        return init_data
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})


# ─── User ─────────────────────────────────────────────────────────────────────


async def get_or_create_user(
    telegram_id: int,
    full_name: str,
    username: Optional[str] = None,
    language_code: str = "ru",
) -> User:
    user, created = await User.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "full_name": full_name,
            "username": username,
            "language_code": language_code,
            "last_active_at": datetime.now(timezone.utc),
        },
    )

    if not created:
        update: dict = {"last_active_at": datetime.now(timezone.utc)}
        if user.full_name != full_name:
            update["full_name"] = full_name
        if username is not None and user.username != username:
            update["username"] = username
        if language_code and user.language_code != language_code:
            update["language_code"] = language_code
        await User.filter(telegram_id=telegram_id).update(**update)
        await user.refresh_from_db()

    return user


async def get_current_user(
    auth_data: WebAppInitData = Depends(auth),
) -> User:
    """
    Единая зависимость: auth + get_or_create_user в одном шаге.

    Использование:
        @router.get("/endpoint")
        async def handler(user: User = Depends(get_current_user)):
            ...

    Заменяет бывший паттерн:
        auth_data = Depends(auth)
        user = await get_or_create_user(auth_data.user.id, ...)
    """
    tg = auth_data.user
    return await get_or_create_user(
        telegram_id=tg.id,
        full_name=tg.first_name or "Unknown",
        username=tg.username,
        language_code=tg.language_code or "ru",
    )
