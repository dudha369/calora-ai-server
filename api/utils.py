from fastapi import Request, HTTPException

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data

from config_reader import config

from db import User

def auth(request: Request) -> WebAppInitData:
    try:
        auth_string = request.headers.get("initData")
        if auth_string:
            data = safe_parse_webapp_init_data(
                config.BOT_TOKEN.get_secret_value(),
                auth_string,
            )

            return data

        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized"},
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized"},
        )

async def check_user(user_id: int, first_name: str | None = None):
    user = await User.get_or_none(id=user_id)

    if user:
        return user

    return await User.create(
        id=user_id,
        name=first_name or "Unknown"
    )
