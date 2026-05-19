from fastapi import Request, HTTPException

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data

from config_reader import config

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

async def check_user(user_id: int) -> User:
    user = await User.get_or_none(id=user_id)

    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized"},
        )

    return user
