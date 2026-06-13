"""
Общие эндпоинты: health check и Telegram webhook.
"""

import asyncio
import hashlib
import logging

from fastapi import APIRouter, Request, HTTPException

from config import config
from bot_instance import bot, dp

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Webhook secret token ────────────────────────────────────────────────────

# Детерминированный токен из BOT_TOKEN — не нужно добавлять лишнюю env-переменную.
# SHA-256 гарантирует что только владелец BOT_TOKEN знает правильный secret.
WEBHOOK_SECRET = hashlib.sha256(
    f"calora-webhook:{config.BOT_TOKEN.get_secret_value()}".encode()
).hexdigest()


@router.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok"}


@router.post("/webhook")
async def webhook(request: Request):
    # ── Проверяем secret_token ──
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        data = await request.json()
        from aiogram.types import Update

        update = Update.model_validate(data, context={"bot": bot})
        asyncio.create_task(_process_update(update))
    except HTTPException:
        raise
    except Exception:
        logger.error("Webhook parse error", exc_info=True)
        # Не возвращаем str(e) — это утечка внутренней информации.
        # Telegram повторит доставку если вернуть не-2xx, но ошибка парсинга
        # = битый запрос, повтор не поможет.
        return {"status": "error"}

    return {"status": "ok"}


async def _process_update(update):
    try:
        await asyncio.wait_for(dp.feed_update(bot, update), timeout=10)
    except Exception as e:
        logger.error(
            "Process update error (update_id=%s): %s",
            update.update_id,
            e,
            exc_info=True,
        )
