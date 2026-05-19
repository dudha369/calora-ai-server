from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards import main_markup
from db import User

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await User.get_or_create(
        id=message.from_user.id,
        defaults={
            "name": message.from_user.first_name
        }
    )

    await message.answer("Hello!")
