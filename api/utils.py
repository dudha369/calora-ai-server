from fastapi import Request, HTTPException
from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from config_reader import config
from db import User

from typing import Any, Optional


def auth(request: Request) -> Optional[WebAppInitData]:
    """Валидирует Telegram initData из заголовка."""

    if request.method == "OPTIONS":
        return None

    try:
        auth_string = request.headers.get("initData")
        if not auth_string:
            raise HTTPException(status_code=401, detail={"error": "Unauthorized"})
        return safe_parse_webapp_init_data(
            config.BOT_TOKEN.get_secret_value(), auth_string
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})


async def get_or_create_user(
    telegram_id: int,
    full_name: str,
    username: Any[str, None] = None,
    language_code: str = "ru",
) -> User:
    """
    Возвращает существующего пользователя или создаёт нового.
    При каждом запросе обновляет full_name и username.
    """
    user, created = await User.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "full_name": full_name,
            "username": username,
            "language_code": language_code,
        },
    )

    if not created:
        await User.filter(telegram_id=telegram_id).update(
            full_name=full_name,
            username=username,
        )
        await user.refresh_from_db()

    return user
