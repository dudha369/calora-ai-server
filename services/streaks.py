"""
Логика стрика: продление/откат событием (после лога/удаления еды) +
ленивое обнаружение обрыва (при чтении данных пользователя) +
ручное восстановление серии.

Жизненный цикл щитов (два независимых триггера сброса):
  1. Новый месяц → streak_restores_available = MAX_RESTORES_PER_MONTH,
     независимо от серии. Отслеживается через streak_restores_reset_at.
  2. Новая серия (current_streak: 0 → 1) → тоже MAX, всегда.
     Новая серия — чистый старт, щиты не переносятся из прошлой.

Примеры:
  • Использовал 1 щит, серия идёт → 2 щита остаются
  • Потерял серию (любое кол-во щитов), начал новую → всегда 3 щита
  • Новый месяц, серия продолжается → всегда 3 щита

Критерий "успешного дня":
  total_calories за день попадает в ±10% от DailyGoal.calories
  (с нюансами по goal_type — см. _day_goal_met).

Ключевые поля User:
  last_streak_check_date    — последняя дата, за которую серия учтена.
  streak_before_break       — значение серии до первого обрыва текущего
                              эпизода. Устанавливается reconcile, сбрасывается
                              при restore или начале новой серии.
  streak_restores_available — остаток щитов.
  streak_restores_reset_at  — первое число месяца, когда щиты выданы.

StreakDay — построчная история для StreakPopup (см. db/models/streak_day.py):
  каждый финализированный день получает статус 'met'/'missed', а
  restore_streak задним числом переводит подряд идущие 'missed' в 'restored'.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import User, DailyGoal, FoodLog, Quest, StreakDay

logger = logging.getLogger(__name__)

CALORIE_TOLERANCE_PCT = 0.10
STARVATION_TOLERANCE_PCT = 0.30
MAX_BACKFILL_DAYS = 365
MAX_RESTORES_PER_MONTH = 3


# ─── Internal helpers ─────────────────────────────────────────────────────────


def local_today(tz_name: str) -> date:
    """
    Текущая дата в локальном времени пользователя.
    Публичная: patch("services.streaks.local_today", ...) в тестах
    подменяет дату для всех функций модуля сразу.
    """
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(tz).date()


def _maybe_refill_restores(user: User, today: date) -> bool:
    """
    Ежемесячный сброс щитов. Возвращает True если что-то изменилось.

    Сравниваем с первым числом текущего месяца — одно поле вместо пары
    (month, year), нет риска ошибки при переходе декабрь → январь.
    """
    this_month = today.replace(day=1)
    if user.streak_restores_reset_at == this_month:
        return False
    user.streak_restores_available = MAX_RESTORES_PER_MONTH
    user.streak_restores_reset_at = this_month
    return True


async def _day_goal_met(user_id: int, day: date, goal: DailyGoal, goal_type: str) -> bool:
    """Умная проверка выполнения цели в зависимости от её типа."""
    logs = await FoodLog.filter(user_id=user_id, log_date=day).all()
    if not logs:
        return False
    total = sum(log.total_calories for log in logs)

    tolerance = goal.calories * CALORIE_TOLERANCE_PCT
    calories_min = goal.calories - tolerance
    calories_max = goal.calories + tolerance

    if goal_type == "gain":
        # Набор массы: главное не недобрать. Перебор не наказывается.
        return total >= calories_min
    elif goal_type == "lose":
        # Похудение: строгий верхний лимит (+10%), но нижний лимит расширен до -30%
        starvation_min = goal.calories * (1 - STARVATION_TOLERANCE_PCT)
        return starvation_min <= total <= calories_max
    else:
        # Поддержание (maintain): классический коридор ±10%
        return calories_min <= total <= calories_max


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


# ─── StreakDay history helpers ─────────────────────────────────────────────────


async def _record_day_result(user_id: int, day: date, status: str) -> None:
    """Апсертит статус дня ('met'/'missed'). Идемпотентно."""
    obj, created = await StreakDay.get_or_create(
        user_id=user_id, log_date=day, defaults={"status": status}
    )
    if not created and obj.status != status:
        obj.status = status
        await obj.save()


async def _clear_day_result(user_id: int, day: date) -> None:
    """
    Удаляет запись дня — используется когда 'сегодня' откатывается с 'met'
    обратно в неопределённое состояние (день ещё не закончился, значит его
    рано фиксировать как финальный).
    """
    await StreakDay.filter(user_id=user_id, log_date=day).delete()


async def _mark_break_as_restored(user_id: int, today: date) -> None:
    """
    Переводит непрерывную цепочку 'missed' дней перед сегодня в 'restored' —
    именно эти дни простил использованный щит. Останавливается на первом дне
    со статусом, отличным от 'missed', или дне без записи вовсе.
    """
    cursor = today - timedelta(days=1)
    while True:
        day_row = await StreakDay.get_or_none(user_id=user_id, log_date=cursor)
        if not day_row or day_row.status != StreakDay.STATUS_MISSED:
            break
        day_row.status = StreakDay.STATUS_RESTORED
        await day_row.save()
        cursor -= timedelta(days=1)


async def get_week_history(user_id: int, tz_name: str, num_days: int = 7) -> list[dict]:
    """
    Последние num_days календарных дней (включая сегодня) со статусом каждого:
    'met' | 'missed' | 'restored' | 'none' (нет записи — день не финализирован
    или предшествует началу истории пользователя).
    """
    today = local_today(tz_name)
    start = today - timedelta(days=num_days - 1)
    records = await StreakDay.filter(
        user_id=user_id, log_date__gte=start, log_date__lte=today
    ).all()
    by_date = {r.log_date: r.status for r in records}
    return [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "status": by_date.get(start + timedelta(days=i), "none"),
        }
        for i in range(num_days)
    ]


# ─── Core logic ───────────────────────────────────────────────────────────────


async def reconcile_streak(user: User, tz_name: str, goal: DailyGoal, goal_type: str) -> bool:
    """
    Закрывает все прошедшие дни до сегодняшней локальной даты.
    Вызывается на GET /me и GET /api/users/streak.

    Ежемесячный сброс щитов проверяется здесь же: даже если pending_days == 0
    (быстрый путь), новый месяц должен отразиться немедленно.
    """
    today = local_today(tz_name)
    refilled = _maybe_refill_restores(user, today)

    last_checked = user.last_streak_check_date or (today - timedelta(days=1))
    pending_days = (today - last_checked).days - 1

    if pending_days <= 0:
        if refilled:
            await user.save()
        return refilled

    streak_before = user.current_streak

    if pending_days > MAX_BACKFILL_DAYS:
        logger.warning(
            "User %s: %d pending days — resetting as corrupted state.",
            user.telegram_id,
            pending_days,
        )
        user.current_streak = 0
        user.streak_before_break = None
    else:
        cursor = last_checked + timedelta(days=1)
        while cursor < today:
            day_met = await _day_goal_met(user.telegram_id, cursor, goal, goal_type)
            if day_met:
                user.current_streak += 1
                user.max_streak = max(user.max_streak, user.current_streak)
                if user.streak_before_break is not None:
                    user.streak_before_break = None
                await _record_day_result(user.telegram_id, cursor, StreakDay.STATUS_MET)
            else:
                if user.current_streak > 0 and user.streak_before_break is None:
                    user.streak_before_break = user.current_streak
                user.current_streak = 0
                await _record_day_result(user.telegram_id, cursor, StreakDay.STATUS_MISSED)
            cursor += timedelta(days=1)

    user.last_streak_check_date = today - timedelta(days=1)
    await _sync_streak_quest(user)
    await user.save()
    return user.current_streak != streak_before or refilled


async def sync_today_credit_state(
    user: User, goal: DailyGoal, tz_name: str, log_date: date, goal_type: str
) -> None:
    """
    Синхронизирует кредит за сегодня после создания/удаления FoodLog.

    Сброс щитов при новой серии: новая серия — всегда чистый старт,
    щиты сбрасываются до MAX независимо от остатка. Нет смысла
    переносить: новая серия = новые условия.
    """
    today = local_today(tz_name)
    if log_date != today:
        return

    await reconcile_streak(user, tz_name, goal, goal_type)

    goal_met = await _day_goal_met(user.telegram_id, today, goal, goal_type)
    already_credited = user.last_streak_check_date == today

    if goal_met and not already_credited:
        starting_fresh = user.current_streak == 0
        user.current_streak += 1
        user.max_streak = max(user.max_streak, user.current_streak)
        user.last_streak_check_date = today
        user.streak_before_break = None

        if starting_fresh:
            # Новая серия — всегда полный комплект щитов.
            user.streak_restores_available = MAX_RESTORES_PER_MONTH

        await _sync_streak_quest(user)
        await user.save()
        await _record_day_result(user.telegram_id, today, StreakDay.STATUS_MET)

    elif not goal_met and already_credited:
        user.current_streak = max(user.current_streak - 1, 0)
        user.last_streak_check_date = today - timedelta(days=1)
        await _sync_streak_quest(user)
        await user.save()
        # День ещё не закончился — не фиксируем его как 'missed' задним числом.
        await _clear_day_result(user.telegram_id, today)


# ─── Read-only ────────────────────────────────────────────────────────────────


def is_streak_active_today(user: User, tz_name: str) -> bool:
    return user.last_streak_check_date == local_today(tz_name)


async def get_today_progress(user_id: int, tz_name: str, goal: DailyGoal, goal_type: str) -> dict:
    today = local_today(tz_name)
    logs = await FoodLog.filter(user_id=user_id, log_date=today).all()
    calories = sum(log.total_calories for log in logs)

    tolerance = round(goal.calories * CALORIE_TOLERANCE_PCT)
    calories_min = goal.calories - tolerance
    calories_max = goal.calories + tolerance

    if goal_type == "gain":
        if calories < calories_min:
            status, calories_remaining = "below", calories_min - calories
        else:
            status, calories_remaining = "met", 0

    elif goal_type == "lose":
        starvation_min = round(goal.calories * (1 - STARVATION_TOLERANCE_PCT))
        if calories < starvation_min:
            status, calories_remaining = "below", starvation_min - calories
        elif calories > calories_max:
            status, calories_remaining = "over", 0
        else:
            status, calories_remaining = "met", 0
        # Для UI-прогрессбара "зеленая зона" начинается от starvation_min
        calories_min = starvation_min

    else:
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


# ─── Restore ─────────────────────────────────────────────────────────────────


async def restore_streak(user: User, tz_name: str) -> dict:
    """
    Восстанавливает серию после разрыва, расходуя один щит.

    Задним числом переводит подряд идущие 'missed' дни (StreakDay) в
    'restored' — именно эту цепочку и простил щит. Перед проверкой
    availability вызываем _maybe_refill_restores — если наступил новый
    месяц, пользователь получает свежие щиты и может воспользоваться ими
    сразу, без лишнего запроса.
    """
    today = local_today(tz_name)
    _maybe_refill_restores(user, today)

    if user.streak_before_break is None:
        return {"ok": False, "reason": "no_break_to_restore"}

    if user.streak_restores_available <= 0:
        return {"ok": False, "reason": "no_restores_available"}

    restored_to = user.streak_before_break
    user.current_streak = restored_to
    user.streak_before_break = None
    user.last_streak_check_date = today - timedelta(days=1)
    user.streak_restores_available -= 1

    await _sync_streak_quest(user)
    await user.save()
    await _mark_break_as_restored(user.telegram_id, today)

    return {
        "ok": True,
        "restored_to": restored_to,
        "restores_remaining": user.streak_restores_available,
    }