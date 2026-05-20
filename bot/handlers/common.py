from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

import asyncio
import asyncpg

from ..keyboards import main_markup
from db import User

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        text="Open the mini-app!",
        reply_markup=main_markup
    )

    asyncio.create_task(save_user(message))


async def save_user(message: Message):
    try:
        await asyncio.wait_for(
            User.get_or_create(
                id=message.from_user.id,
                defaults={
                    "name": message.from_user.first_name or "Unknown"
                }
            ),
            timeout=2.0
        )
    except Exception as e:
        print("DB ERROR:", e)
