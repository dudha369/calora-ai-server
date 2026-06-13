import asyncio
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards import main_markup
from config import config
from bot_instance import bot
from db import User

logger = logging.getLogger(__name__)
router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user

    is_new = await _save_user(message)

    in_whitelist = (
        not config.WHITELIST_ENABLED
        or user.id in config.whitelist_ids
    )

    if is_new and config.ADMIN_TELEGRAM_ID:
        asyncio.create_task(_notify_admin(user.id, user.first_name, user.username, in_whitelist))

    if not in_whitelist:
        await message.answer(
            "🚫 *Access denied*\n\n"
            "You are not on the access list for this application.\n"
            "Please contact the administrator.",
            parse_mode="Markdown",
        )
        return

    await message.answer("👋 Hello!\n💚 Open the mini-app:", reply_markup=main_markup)


async def _save_user(message: Message) -> bool:
    """Save user to DB. Returns True if the user was just created."""
    user = message.from_user
    try:
        _, created = await asyncio.wait_for(
            User.get_or_create(
                telegram_id=user.id,
                defaults={
                    "full_name": user.first_name or "Unknown",
                    "username": user.username,
                    "language_code": user.language_code,
                },
            ),
            timeout=3.0,
        )
        return created
    except Exception as e:
        logger.error("DB error saving user %s: %s", user.id, e, exc_info=True)
        return False


async def _notify_admin(
    user_id: int,
    full_name: str,
    username: str | None,
    in_whitelist: bool,
) -> None:
    """Send a new-user notification to the admin."""
    status = "✅ в whitelist" if in_whitelist else "🚫 не в whitelist"
    username_line = f"@{username}" if username else "—"

    text = (
        "👤 *Новый пользователь запустил бота*\n\n"
        f"• ID: `{user_id}`\n"
        f"• Имя: {full_name}\n"
        f"• Ник: {username_line}\n"
        f"• Доступ: {status}"
    )

    try:
        await bot.send_message(
            chat_id=config.ADMIN_TELEGRAM_ID,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Admin notify error for user %s: %s", user_id, e, exc_info=True)
