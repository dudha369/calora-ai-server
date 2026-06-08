from pathlib import Path
from typing import AsyncGenerator

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from tortoise import Tortoise

ROOT_DIR = Path(__file__).parent.absolute()


class Config(BaseSettings):
    BOT_TOKEN: SecretStr
    DB_URL: SecretStr
    GEMINI_API_KEY: SecretStr

    WEBHOOK_URL: SecretStr
    WEBAPP_URL: SecretStr

    APP_HOST: str = "localhost"
    APP_PORT: int = 8080

    B2_ENDPOINT: str = ""
    B2_KEY_ID: SecretStr = SecretStr("")
    B2_APPLICATION_KEY: SecretStr = SecretStr("")
    B2_BUCKET: str = ""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_override_existing=True,
    )


config = Config()

TORTOISE_ORM = {
    "connections": {"default": config.DB_URL.get_secret_value()},
    "apps": {
        "models": {
            "models": [
                "db.models.user",
                "db.models.user_profile",
                "db.models.onboarding_draft",
                "db.models.daily_goal",
                "db.models.weight_history",
                "db.models.food_log",
                "db.models.food_item",
                "db.models.water_log",
                "db.models.quest",
                "db.models.ai_tip",
                "aerich.models",
            ],
            "default_connection": "default",
        }
    },
}


async def lifespan(app: FastAPI) -> AsyncGenerator:
    webhook_url = config.WEBHOOK_URL.get_secret_value().rstrip("/")
    await bot.set_webhook(
        url=f"{webhook_url}/webhook",
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )

    await Tortoise.init(TORTOISE_ORM)

    yield

    await bot.session.close()
    await Tortoise.close_connections()


bot = Bot(config.BOT_TOKEN.get_secret_value())
dp = Dispatcher()
app = FastAPI(lifespan=lifespan)
