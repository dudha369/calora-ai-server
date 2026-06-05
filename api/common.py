import asyncio
from fastapi import APIRouter, Request
from aiogram.types import Update
from config_reader import bot, dp

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
        print("WEBHOOK ERROR:", e)

    return {"status": "ok"}


async def _process_update(update: Update):
    try:
        await asyncio.wait_for(dp.feed_update(bot, update), timeout=10)
    except Exception as e:
        print("PROCESS UPDATE ERROR:", e)
