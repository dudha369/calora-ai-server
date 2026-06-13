"""
Общие эндпоинты: health check и Telegram webhook.
"""

import asyncio
import logging

from fastapi import APIRouter, Request
from aiogram.types import Update
from bot_instance import bot, dp

logger = logging.getLogger(__name__)
router = APIRouter()


@router.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok"}


@router.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        asyncio.create_task(_process_update(update))
    except Exception as e:
        logger.error("Webhook error: %s", e, exc_info=True)
        # Telegram повторит доставку если вернуть не-2xx, но на практике
        # ошибка парсинга = битый запрос, повтор не поможет.
        return {"status": "error", "detail": str(e)}

    return {"status": "ok"}


async def _process_update(update: Update):
    try:
        await asyncio.wait_for(dp.feed_update(bot, update), timeout=10)
    except Exception as e:
        logger.error("Process update error (update_id=%s): %s", update.update_id, e, exc_info=True)
