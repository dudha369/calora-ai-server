from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from tortoise import Tortoise

from bot_instance import bot, dp
from config import TORTOISE_ORM, config
from services.reminders import send_daily_reminders

scheduler = AsyncIOScheduler(timezone="UTC")


async def lifespan(app: FastAPI) -> AsyncGenerator:
    from api.common import WEBHOOK_SECRET

    webhook_url = config.WEBHOOK_URL.get_secret_value().rstrip("/")
    await bot.set_webhook(
        url=f"{webhook_url}/webhook",
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
        secret_token=WEBHOOK_SECRET,
    )
    await Tortoise.init(TORTOISE_ORM)

    # Стрик больше не закрывается батчем (см. services/streaks.py) — этот
    # таймер теперь только под напоминания.
    scheduler.add_job(
        send_daily_reminders,
        trigger="cron",
        minute=5,
        id="daily_reminders",
        max_instances=1,
        misfire_grace_time=600,
    )
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)
    await bot.session.close()
    await Tortoise.close_connections()


app = FastAPI(lifespan=lifespan)
