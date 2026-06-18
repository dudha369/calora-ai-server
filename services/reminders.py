"""
Напоминания пользователям, которые рискуют не дотянуть до дневной нормы.

Это каркас: инфраструктура (расписание, локальный час пользователя) уже на
месте, критерии "кому и когда слать" — заглушка с явными TODO.

Почему это всё-таки почасовой обход ВСЕХ пользователей, в отличие от
services/streaks.py: напоминание по определению нужно тому, кто СЕЙЧАС не
в приложении — если он сам зайдёт, напоминание уже не нужно. Это единственный
сценарий, где обход по таймеру оправдан.
"""

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import UserProfile, DailyGoal, FoodLog
from bot_instance import bot

logger = logging.getLogger(__name__)

# TODO: вынести в конфиг, когда появится реальная логика.
REMINDER_LOCAL_HOUR = 20  # шлём тем, у кого сейчас ~20:00 по их поясу


def _local_hour(tz_name: str) -> int:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(tz).hour


async def _needs_reminder(user_id: int) -> bool:
    """
    TODO заглушка — сейчас проверяет только "залогировал хоть что-то сегодня".
    Перед продом точно нужно добавить:
      • поле-флаг типа User.last_reminder_sent_date (по аналогии с
        last_streak_check_date) — иначе будет слать КАЖДЫЙ час в течение
        всего окна, пока юзер не залогирует;
      • проверку "набрал ли уже норму", а не просто "есть запись";
      • текст с упоминанием User.current_streak, если он под угрозой.
    """
    return not await FoodLog.filter(user_id=user_id, log_date=date.today()).exists()


async def send_daily_reminders() -> dict:
    """Раз в час проверяет, для кого сейчас REMINDER_LOCAL_HOUR в их
    локальном времени, и шлёт напоминание через Telegram-бота."""
    sent = 0

    profiles = await UserProfile.all().values_list("user_id", "timezone")
    for user_id, tz_name in profiles:
        if _local_hour(tz_name) != REMINDER_LOCAL_HOUR:
            continue
        if not await DailyGoal.filter(user_id=user_id).exists():
            continue
        if not await _needs_reminder(user_id):
            continue

        try:
            await bot.send_message(
                chat_id=user_id,
                text="Не забудь залогировать сегодняшнюю еду 🌱",
            )
            sent += 1
        except Exception:
            logger.warning("Reminder failed for user %s", user_id, exc_info=True)

    return {"sent": sent}
