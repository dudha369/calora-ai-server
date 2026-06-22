"""
Логика стрика: продление/откат событием (после лога/удаления еды) +
ленивое обнаружение обрыва (при чтении данных пользователя). Никакого
батча по всем юзерам — стрик полностью event-driven.

  • продление/откат — POST /api/food/log[-barcode] и DELETE /api/food/{id}
    дёргают одну и ту же sync_today_credit_state: она смотрит на факт
    (выполнена ли норма сегодня прямо сейчас) и либо начисляет кредит,
    либо снимает, либо ничего не делает. Это заменило собой две раздельные
    функции (credit/uncredit), у которых был пробел: переедание → удаление
    лишней записи → возврат в норму не давало кредита, пока пользователь
    не сделает ещё один POST. Симметричная проверка закрывает это для
    обоих направлений одним кодом.
  • обрыв — обнаруживается лениво, в местах, которые читают
    User.current_streak: GET /api/users/me, GET /api/users/streak и
    GET /api/admin/users/{id}. Раз пользователь не дологировал — события,
    на которое можно было бы среагировать сразу, просто не происходит,
    поэтому обрыв ловится не "в моменте", а при следующем чтении.

Критерий "успешного дня" (совпадает с quest_key='calorie_goal' из quest.py):
  total_calories за день попадает в ±10% от DailyGoal.calories.

Идемпотентность:
  User.last_streak_check_date — последняя дата (в локальном времени
  пользователя), за которую серия уже учтена. Может указывать на СЕГОДНЯ
  (кредит уже выдан в течение дня) или на день до границы reconcile.

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


def local_today(tz_name: str) -> date:
    """
    Текущая календарная дата в локальном времени пользователя.

    Публичная (без подчёркивания), потому что переиспользуется не только
    внутри этого модуля: GET /api/users/streak отдаёт прогресс за "сегодня"
    через get_today_progress ниже — но именно тот вызов остаётся ВНУТРИ
    этого файла, а не в api/users.py, ровно чтобы patch("services.streaks
    .local_today", ...) в тестах одинаково подменял дату для reconcile,
    sync_today_credit_state и get_today_progress.
    """
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
    даты). Сегодняшний день не трогает — это работа sync_today_credit_state.

    Самый частый случай (юзер уже заходил сегодня или вчера) выходит после
    одного сравнения дат, без единого запроса к БД.
    """
    today = local_today(tz_name)
    last_checked = user.last_streak_check_date or (today - timedelta(days=1))
    pending_days = (today - last_checked).days - 1

    if pending_days <= 0:
        return False

    streak_before = user.current_streak

    if pending_days > MAX_BACKFILL_DAYS:
        logger.warning(
            "User %s has %d pending days — treating as corrupted state",
            user.telegram_id,
            pending_days,
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


async def sync_today_credit_state(
    user: User, goal: DailyGoal, tz_name: str, log_date: date
) -> None:
    """
    Единая точка синхронизации кредита за сегодня — вызывается и после
    создания, и после удаления FoodLog. Смотрит на факт ("выполнена ли
    норма прямо сейчас") и либо начисляет, либо снимает кредит, либо не
    делает ничего, если состояние уже соответствует факту.

    Не реагирует на log_date в прошлом — обработка прошлых дней это
    отдельно работа reconcile_streak, не эта функция.
    """
    today = local_today(tz_name)
    if log_date != today:
        return

    await reconcile_streak(user, tz_name, goal)

    goal_met = await _day_goal_met(user.telegram_id, today, goal)
    already_credited = user.last_streak_check_date == today

    if goal_met and not already_credited:
        user.current_streak += 1
        user.max_streak = max(user.max_streak, user.current_streak)
        user.last_streak_check_date = today
        await _sync_streak_quest(user)
        await user.save()
    elif not goal_met and already_credited:
        user.current_streak = max(user.current_streak - 1, 0)
        user.last_streak_check_date = today - timedelta(days=1)
        await _sync_streak_quest(user)
        await user.save()
    # иначе: текущее состояние уже соответствует факту, ничего не делаем


def is_streak_active_today(user: User, tz_name: str) -> bool:
    """True, если кредит за сегодня уже выдан."""
    return user.last_streak_check_date == local_today(tz_name)


async def get_today_progress(user_id: int, tz_name: str, goal: DailyGoal) -> dict:
    """
    Прогресс по калориям за сегодня относительно допустимого диапазона
    (±CALORIE_TOLERANCE_PCT от DailyGoal.calories). Используется попапом
    "Серия" на HomePage (GET /api/users/streak), чтобы показать, сколько
    ещё нужно набрать, или что норма уже превышена.

    Принимает user_id (не полный User), потому что только читает данные —
    мутаций здесь нет, в отличие от reconcile_streak/sync_today_credit_state.
    """
    today = local_today(tz_name)
    logs = await FoodLog.filter(user_id=user_id, log_date=today).all()
    calories = sum(log.total_calories for log in logs)

    tolerance = round(goal.calories * CALORIE_TOLERANCE_PCT)
    calories_min = goal.calories - tolerance
    calories_max = goal.calories + tolerance

    if calories < calories_min:
        status, calories_remaining = "below", calories_min - calories
    elif calories > calories_max:
        status, calories_remaining = "over", 0
    else:
        status, calories_remaining = "met", 0

    return {
        "calories": calories,
        "calories_goal": goal.calories,
        "calories_min": calories_min,
        "calories_max": calories_max,
        "calories_remaining": calories_remaining,
        "status": status,
    }
