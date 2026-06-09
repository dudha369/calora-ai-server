import asyncio
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards import main_markup
from config_reader import config
from db import User

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if config.WHITELIST_ENABLED and message.from_user.id not in config.whitelist_ids:
        await message.answer(
            "🚫 *Access denied*\n\n"
            "You are not on the access list for this application.\n"
            "Please contact the administrator.",
            parse_mode="Markdown",
        )
        return

    await message.answer("👋 Hello!\n💚 Open the mini-app:", reply_markup=main_markup)

    asyncio.create_task(_save_user(message))


async def _save_user(message: Message):
    try:
        await asyncio.wait_for(
            User.get_or_create(
                telegram_id=message.from_user.id,
                defaults={
                    "full_name": message.from_user.first_name or "Unknown",
                    "username": message.from_user.username,
                    "language_code": message.from_user.language_code,
                },
            ),
            timeout=2.0,
        )
    except Exception as e:
        print("DB ERROR:", e)
