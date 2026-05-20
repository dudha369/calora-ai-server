from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from db import User

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    try:
        await User.get_or_create(
            id=message.from_user.id,
            defaults={
                "name": message.from_user.first_name or "Unknown",
            },
        )
    except Exception as e:
        print(f"DB error in /start: {e}")
    finally:
        await message.answer(
            text="Open the mini-app!",
            reply_markup=main_markup
        )
