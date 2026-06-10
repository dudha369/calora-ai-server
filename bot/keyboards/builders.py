from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import config

main_markup = (
    InlineKeyboardBuilder().button(
        text="🌱 Open", web_app=WebAppInfo(url=config.WEBAPP_URL.get_secret_value())
    )
).as_markup()
