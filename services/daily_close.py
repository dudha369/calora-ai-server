"""
Ежедневное закрытие дня: обновление User.current_streak / max_streak
и синхронизация квестов с quest_key='streak'.

Запускается:
  • автоматически — APScheduler, см. app.py (каждый час, в :05)
  • вручную — POST /api/admin/cron/close-streaks (для отладки/ops)

Почему этот модуль лежит в services/, а не в ai/services/:
  Здесь нет ни одного вызова Gemini — это чистый расчёт по уже имеющимся
  в БД данным. ai/services/ зарезервирован за модулями, которые реально
  обращаются к ai/gemini.py; смешивать с ними эту логику было бы
  архитектурно неверно и вводило бы в заблуждение при чтении импортов.

Критерий "успешного дня" (совпадает с quest_key='calorie_goal' из quest.py):
  total_calories за день попадает в ±10% от DailyGoal.calories.
  День без DailyGoal или без единой записи FoodLog считается невыполненным.

Идемпотентность:
  User.last_streak_check_date хранит последнюю обработанную календарную
  дату пользователя в его локальном времени (UserProfile.timezone).
  Повторный прогон для уже обработанной даты становится no-op.

Устойчивость к простою:
  Если cron не запускался несколько дней, пропущенные дни проигрываются
  по очереди на основе реальных FoodLog за каждый день — стрик не "теряется"
  только из-за того, что джоба была недоступна. MAX_BACKFILL_DAYS — это
  защита не от обычного простоя, а от аномальных данных (например, если
  last_streak_check_date оказался в далёком прошлом); в норме этот предел
  никогда не достигается.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import User, UserProfile, DailyGoal, FoodLog, Quest

logger = logging.getLogger(__name__)

CALORIE_TOLERANCE_PCT = 0.10
MAX_BACKFILL_DAYS = 365


def _local_today(tz_name: str) -> date:
    """Текущая календарная дата в локальной таймзоне пользователя."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(tz).date()


async def _day_goal_met(user_id: int, day: date, goal: DailyGoal) -> bool:
    """Достигнута ли калорийная цель (±10%) за конкретный день."""
    logs = await FoodLog.filter(user_id=user_id, log_date=day).all()
    if not logs:
        return False
    total_calories = sum(log.total_calories for log in logs)
    tolerance = goal.calories * CALORIE_TOLERANCE_PCT
    return abs(total_calories - goal.calories) <= tolerance


async def _sync_streak_quest(user: User) -> None:
    """quest_key='streak' всегда зеркалит текущее значение User.current_streak."""
    quests = await Quest.filter(
        user_id=user.telegram_id,
        quest_key="streak",
        status=Quest.STATUS_ACTIVE,
    ).all()

    for quest in quests:
        quest.current_value = user.current_streak
        if quest.current_value >= quest.target_value:
            quest.status = Quest.STATUS_DONE
            quest.completed_at = datetime.now(timezone.utc)
            user.quests_completed += 1
        await quest.save()


async def _close_days_for_user(user: User, tz_name: str, goal: DailyGoal) -> None:
    local_today = _local_today(tz_name)
    last_checked = user.last_streak_check_date or (local_today - timedelta(days=1))
    pending_days = (local_today - last_checked).days - 1

    if pending_days <= 0:
        return  # "вчера" уже обработано — новых завершённых дней нет

    if pending_days > MAX_BACKFILL_DAYS:
        logger.warning(
            "User %s has %d pending days — treating as corrupted state",
            user.telegram_id, pending_days,
        )
        user.current_streak = 0
    else:
        cursor = last_checked + timedelta(days=1)
        while cursor < local_today:
            if await _day_goal_met(user.telegram_id, cursor, goal):
                user.current_streak += 1
                user.max_streak = max(user.max_streak, user.current_streak)
            else:
                user.current_streak = 0
            cursor += timedelta(days=1)

    user.last_streak_check_date = local_today - timedelta(days=1)
    await _sync_streak_quest(user)
    await user.save()


async def close_completed_days() -> dict:
    """
    Точка входа джобы: обходит всех пользователей с профилем и целями
    и закрывает для каждого все полностью завершённые, но ещё не
    обработанные дни в его локальном времени.
    """
    profiles = await UserProfile.all().values_list("user_id", "timezone")
    if not profiles:
        return {"processed": 0, "streak_broken": 0}

    user_ids = [user_id for user_id, _ in profiles]
    tz_by_user = dict(profiles)

    # Две bulk-выборки вместо N+1: независимо от числа пользователей — это
    # всего 3 запроса к БД суммарно за весь прогон джобы.
    users_by_id = {
        u.telegram_id: u for u in await User.filter(telegram_id__in=user_ids)
    }
    goals_by_id = {
        g.user_id: g for g in await DailyGoal.filter(user_id__in=user_ids)
    }

    processed = 0
    streak_broken = 0

    for user_id in user_ids:
        user = users_by_id.get(user_id)
        goal = goals_by_id.get(user_id)
        if not user or not goal:
            continue  # онбординг не завершён или цели ещё не рассчитаны

        streak_before = user.current_streak
        try:
            await _close_days_for_user(user, tz_by_user[user_id], goal)
        except Exception:
            logger.exception("daily_close failed for user %s", user_id)
            continue

        if user.current_streak != streak_before:
            processed += 1
            if user.current_streak == 0 and streak_before > 0:
                streak_broken += 1

    return {"processed": processed, "streak_broken": streak_broken}
