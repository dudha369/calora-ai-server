from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from tortoise import Tortoise

from bot_instance import bot, dp
from config import TORTOISE_ORM, config
from services.daily_close import close_completed_days

# Один процесс — один scheduler. AsyncIOScheduler работает на том же event
# loop, что и uvicorn, без отдельных потоков/процессов.
scheduler = AsyncIOScheduler(timezone="UTC")


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

    # Раз в час, на 5-й минуте. max_instances=1 не даёт двум прогонам
    # пересечься, если предыдущий не успел закрыться за час (защита от
    # гонок при записи одной и той же строки User).
    scheduler.add_job(
        close_completed_days,
        trigger="cron",
        minute=5,
        id="daily_close",
        max_instances=1,
        misfire_grace_time=600,
    )
    scheduler.start()

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    await bot.session.close()
    await Tortoise.close_connections()


app = FastAPI(lifespan=lifespan)
