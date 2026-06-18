"""
Логика стрика: продление событием (после лога еды) + ленивое обнаружение
обрыва (при чтении данных пользователя). Никакого батча по всем юзерам —
стрик полностью event-driven.

  • продление — POST /api/food/log[-barcode], сразу как калории за сегодня
    попали в ±10% от DailyGoal.calories;
  • обрыв — обнаруживается лениво, в местах, которые читают
    User.current_streak: GET /api/users/me и GET /api/admin/users/{id}.
    Раз пользователь не дологировал — события, на которое можно было бы
    среагировать сразу, просто не происходит, поэтому обрыв ловится не
    "в моменте", а при следующем чтении.

Критерий "успешного дня" (совпадает с quest_key='calorie_goal' из quest.py):
  total_calories за день попадает в ±10% от DailyGoal.calories.

Идемпотентность:
  User.last_streak_check_date — последняя дата (в локальном времени
  пользователя), за которую серия уже учтена. Может указывать на СЕГОДНЯ
  (кредит уже выдан в течение дня) или на день до границы reconcile.
  Защищает и от повторного начисления при нескольких food/log за день,
  и от повторного обрыва при нескольких /me за день.

MAX_BACKFILL_DAYS — защита не от обычного простоя (он закрывается день за
днём корректно по реальным FoodLog), а от аномальных данных типа
last_streak_check_date в далёком прошлом.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import User, DailyGoal, FoodLog, Quest

logger = logging.getLogger(__name__)

CALORIE_TOLERANCE_PCT = 0.10
MAX_BACKFILL_DAYS = 365


def _local_today(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(tz).date()


async def _day_goal_met(user_id: int, day: date, goal: DailyGoal) -> bool:
    logs = await FoodLog.filter(user_id=user_id, log_date=day).all()
    if not logs:
        return False
    total_calories = sum(log.total_calories for log in logs)
    tolerance = goal.calories * CALORIE_TOLERANCE_PCT
    return abs(total_calories - goal.calories) <= tolerance


async def _sync_streak_quest(user: User) -> None:
    quests = await Quest.filter(
        user_id=user.telegram_id, quest_key="streak", status=Quest.STATUS_ACTIVE
    ).all()
    for quest in quests:
        quest.current_value = user.current_streak
        if quest.current_value >= quest.target_value:
            quest.status = Quest.STATUS_DONE
            quest.completed_at = datetime.now(timezone.utc)
            user.quests_completed += 1
        await quest.save()


async def reconcile_streak(user: User, tz_name: str, goal: DailyGoal) -> bool:
    """
    Закрывает все ПОЛНОСТЬЮ прошедшие дни (строго до сегодняшней локальной
    даты). Сегодняшний день не трогает — это работа credit_today_if_goal_met.

    Самый частый случай (юзер уже заходил сегодня или вчера) выходит после
    одного сравнения дат, без единого запроса к БД — важно, так как вызов
    висит на каждом GET /api/users/me.
    """
    today = _local_today(tz_name)
    last_checked = user.last_streak_check_date or (today - timedelta(days=1))
    pending_days = (today - last_checked).days - 1

    if pending_days <= 0:
        return False

    streak_before = user.current_streak

    if pending_days > MAX_BACKFILL_DAYS:
        logger.warning(
            "User %s has %d pending days — treating as corrupted state",
            user.telegram_id, pending_days,
        )
        user.current_streak = 0
    else:
        cursor = last_checked + timedelta(days=1)
        while cursor < today:
            if await _day_goal_met(user.telegram_id, cursor, goal):
                user.current_streak += 1
                user.max_streak = max(user.max_streak, user.current_streak)
            else:
                user.current_streak = 0
            cursor += timedelta(days=1)

    user.last_streak_check_date = today - timedelta(days=1)
    await _sync_streak_quest(user)
    await user.save()
    return user.current_streak != streak_before


async def credit_today_if_goal_met(
    user: User, goal: DailyGoal, tz_name: str, log_date: date
) -> None:
    """
    Вызывается сразу после сохранения FoodLog. Если log_date — это СЕГОДНЯ в
    локальном времени пользователя, добирает пропущенные прошлые дни и
    выдаёт мгновенный кредит, если калории на сегодня попали в норму.
    Запись задним числом (log_date в прошлом) стрик здесь не продлевает —
    это закроет reconcile_streak при следующем GET /me.
    """
    today = _local_today(tz_name)
    if log_date != today:
        return

    await reconcile_streak(user, tz_name, goal)

    if user.last_streak_check_date == today:
        return  # сегодня уже засчитано — вторая запись еды не задвоит

    if await _day_goal_met(user.telegram_id, today, goal):
        user.current_streak += 1
        user.max_streak = max(user.max_streak, user.current_streak)
        user.last_streak_check_date = today
        await _sync_streak_quest(user)
        await user.save()
