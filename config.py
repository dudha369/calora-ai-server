from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    WHITELIST_ENABLED: bool = False
    WHITELIST_IDS: str = ""
    ADMIN_TELEGRAM_ID: int = 0

    @property
    def whitelist_ids(self) -> set[int]:
        """Return the set of whitelisted Telegram user IDs (parsed from env)."""
        if not self.WHITELIST_IDS.strip():
            return set()
        result: set[int] = set()
        for part in self.WHITELIST_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
        return result

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
                "db.models.app_settings",
                "db.models.broadcast",
                "aerich.models",
            ],
            "default_connection": "default",
        }
    },
}
