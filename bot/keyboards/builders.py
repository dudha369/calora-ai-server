from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config_reader import config

main_markup = (
    InlineKeyboardBuilder()
    .button(text="🌱Open", web_app=WebAppInfo(url=config.WEB_APP_URL))
).as_markup()
