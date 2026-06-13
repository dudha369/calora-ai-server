from typing import AsyncGenerator

from fastapi import FastAPI
from tortoise import Tortoise

from bot_instance import bot, dp
from config import TORTOISE_ORM, config


async def lifespan(app: FastAPI) -> AsyncGenerator:
    # ── Startup ──────────────────────────────────────────────────
    from api.common import WEBHOOK_SECRET

    webhook_url = config.WEBHOOK_URL.get_secret_value().rstrip("/")
    await bot.set_webhook(
        url=f"{webhook_url}/webhook",
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
        secret_token=WEBHOOK_SECRET,
    )
    await Tortoise.init(TORTOISE_ORM)

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    await bot.session.close()
    await Tortoise.close_connections()


app = FastAPI(lifespan=lifespan)
