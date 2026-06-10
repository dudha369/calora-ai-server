from aiogram import Bot, Dispatcher

from config import config

bot = Bot(config.BOT_TOKEN.get_secret_value())
dp = Dispatcher()
