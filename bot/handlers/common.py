from aiogram import Router
from aiogram.filters import CommandStart

from bot.keyboards import main_markup
from db import User

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await User.filter(id=message.from_user.id).exists()
    if not user:
        await User.create(
            id=message.from_user.id,
            name=message.from_user.first_name,
        )

    await message.answer(
        text="Open the mini-app!",
        reply_markup=main_markup
    )
