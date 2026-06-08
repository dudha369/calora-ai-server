from fastapi import Request, HTTPException
from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from config_reader import config
from db import User
from typing import Optional


def auth(request: Request) -> Optional[WebAppInitData]:
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
    username: Optional[str] = None,
    language_code: str = "ru",
) -> User:
    user, created = await User.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "full_name": full_name,
            "username": username,
            "language_code": language_code,
        },
    )

    if not created:
        update = {"full_name": full_name}
        if username is not None:
            update["username"] = username
        if language_code:
            update["language_code"] = language_code
        await User.filter(telegram_id=telegram_id).update(**update)
        await user.refresh_from_db()

    return user
