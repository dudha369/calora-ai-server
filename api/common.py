from fastapi import APIRouter, Request
from aiogram.types import Update
from config_reader import bot, dp

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "ok"}


@router.post("/webhook")
async def webhook(request: Request) -> dict:
    print("WEBHOOK HIT")

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})

        print(f"UPDATE TYPE: {update.event_type}")

        await dp.feed_update(bot, update)

    except Exception as e:
        print(f"WEBHOOK ERROR: {e}")

    return {"status": "ok"}
