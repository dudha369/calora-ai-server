"""
Логика стрика: продление/откат событием (после лога/удаления еды) +
ленивое обнаружение обрыва (при чтении данных пользователя) +
ручное восстановление серии (MAX_RESTORES_PER_STREAK раз за серию).

Жизненный цикл восстановлений:
  • Новая серия (current_streak: 0 → 1) — заряды сбрасываются в MAX.
  • Restore использован — заряд списывается (streak_restores_available -= 1).
  • Серия оборвалась и пользователь начал новую — неиспользованные заряды
    сгорают и выдаются свежие при первом met-дне. Это "щит текущей серии",
    а не месячная подписка.

Почему per-streak, а не per-month:
  Per-month требовал дополнительного поля (streak_restores_reset_at) и
  создавал странную семантику — заряды живут сами по себе независимо от
  серии. Per-streak честнее для пользователя и проще технически: нет
  date-tracking, сброс происходит ровно там, где начинается новая серия.

Ключевые поля User:
  last_streak_check_date    — дата последнего учтённого дня (в tz юзера).
                              == today → сегодня засчитано.
  streak_before_break       — значение серии до первого обрыва текущего
                              эпизода. None → серия активна или эпизод
                              закрыт (восстановлен / начата новая серия).
                              Устанавливается только в reconcile.
  streak_restores_available — остаток зарядов для текущей серии.

MAX_BACKFILL_DAYS — защита от аномальных данных: при last_streak_check_date
в далёком прошлом пересчёт нецелесообразен, сбрасываем в 0.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import User, DailyGoal, FoodLog, Quest

logger = logging.getLogger(__name__)

CALORIE_TOLERANCE_PCT = 0.10
MAX_BACKFILL_DAYS = 365
MAX_RESTORES_PER_STREAK = 2


# ─── Internal helpers ─────────────────────────────────────────────────────────


def local_today(tz_name: str) -> date:
    """
    Текущая календарная дата в локальном времени пользователя.

    Публичная (без подчёркивания): patch("services.streaks.local_today", ...)
    в тестах подменяет дату для всех функций модуля сразу.
    """
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(tz).date()


async def _day_goal_met(user_id: int, day: date, goal: DailyGoal) -> bool:
    """Попадают ли суммарные калории за день в допуск +-10% от цели."""
    logs = await FoodLog.filter(user_id=user_id, log_date=day).all()
    if not logs:
        return False
    total = sum(log.total_calories for log in logs)
    tolerance = goal.calories * CALORIE_TOLERANCE_PCT
    return abs(total - goal.calories) <= tolerance


async def _sync_streak_quest(user: User) -> None:
    """Синхронизирует quest_key='streak' с текущим current_streak."""
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


# ─── Core streak logic ────────────────────────────────────────────────────────


async def reconcile_streak(user: User, tz_name: str, goal: DailyGoal) -> bool:
    """
    Закрывает все ПОЛНОСТЬЮ прошедшие дни (строго до сегодняшней локальной
    даты). Сегодняшний день не трогает — это работа sync_today_credit_state.

    Быстрый путь (юзер уже заходил сегодня или вчера): одно сравнение дат,
    без единого запроса к БД. Важно — функция висит на GET /api/users/me.

    Правила streak_before_break в цикле:
      • Первый переход current_streak > 0 → 0: сохраняем доразрывное
        значение. Только первый переход — чтобы не перетереть при
        нескольких пропущенных днях подряд.
      • Met-день после разрыва: сбрасываем — пользователь начал новую
        серию внутри backfill-окна, старый эпизод потери закрыт.
      • Corrupted state: сбрасываем всё.
    """
    today = local_today(tz_name)
    last_checked = user.last_streak_check_date or (today - timedelta(days=1))
    pending_days = (today - last_checked).days - 1

    if pending_days <= 0:
        return False

    streak_before = user.current_streak

    if pending_days > MAX_BACKFILL_DAYS:
        logger.warning(
            "User %s: %d pending days, treating as corrupted state — resetting.",
            user.telegram_id,
            pending_days,
        )
        user.current_streak = 0
        user.streak_before_break = None
    else:
        cursor = last_checked + timedelta(days=1)
        while cursor < today:
            if await _day_goal_met(user.telegram_id, cursor, goal):
                user.current_streak += 1
                user.max_streak = max(user.max_streak, user.current_streak)
                # Met-день после разрыва — старый эпизод потери закрыт
                if user.streak_before_break is not None:
                    user.streak_before_break = None
            else:
                # Сохраняем только при ПЕРВОМ переходе в 0 в этом эпизоде
                if user.current_streak > 0 and user.streak_before_break is None:
                    user.streak_before_break = user.current_streak
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
    Единая точка синхронизации кредита за сегодня.
    Вызывается после создания И удаления FoodLog — смотрит на факт
    прямо сейчас и приводит состояние в соответствие.

    Сброс восстановлений: происходит здесь при переходе 0 → 1, потому что
    именно здесь семантически "начинается новая серия". Никакого
    отдельного события не нужно — логика там, где происходит переход.

    streak_before_break сбрасывается при кредите: новая серия стартовала,
    старый эпизод потери закрыт, restore к нему больше неприменим.

    Не реагирует на log_date в прошлом — прошлые дни закрывает reconcile.
    """
    today = local_today(tz_name)
    if log_date != today:
        return

    await reconcile_streak(user, tz_name, goal)

    goal_met = await _day_goal_met(user.telegram_id, today, goal)
    already_credited = user.last_streak_check_date == today

    if goal_met and not already_credited:
        starting_fresh = user.current_streak == 0
        user.current_streak += 1
        user.max_streak = max(user.max_streak, user.current_streak)
        user.last_streak_check_date = today
        user.streak_before_break = None

        if starting_fresh:
            # Новая серия — выдаём свежий комплект восстановлений.
            # Неиспользованные заряды от предыдущей серии сгорают.
            user.streak_restores_available = MAX_RESTORES_PER_STREAK

        await _sync_streak_quest(user)
        await user.save()

    elif not goal_met and already_credited:
        user.current_streak = max(user.current_streak - 1, 0)
        user.last_streak_check_date = today - timedelta(days=1)
        # streak_before_break не трогаем: если серия упала до 0,
        # reconcile при следующем чтении корректно сохранит доразрывное
        # значение для restore.
        await _sync_streak_quest(user)
        await user.save()


# ─── Read-only helpers ────────────────────────────────────────────────────────


def is_streak_active_today(user: User, tz_name: str) -> bool:
    """True если кредит за сегодня уже выдан."""
    return user.last_streak_check_date == local_today(tz_name)


async def get_today_progress(user_id: int, tz_name: str, goal: DailyGoal) -> dict:
    """
    Прогресс по калориям за сегодня относительно допуска +-10%.

    Живёт внутри этого модуля (а не в api/users.py), чтобы
    patch("services.streaks.local_today", ...) в тестах корректно
    подменял дату для этой функции тоже.
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


# ─── Restore ─────────────────────────────────────────────────────────────────


async def restore_streak(user: User, tz_name: str) -> dict:
    """
    Восстанавливает серию после разрыва, расходуя один заряд.

    Условия:
      • streak_before_break is not None — есть что восстанавливать
      • streak_restores_available > 0 — есть заряды

    После восстановления last_streak_check_date = вчера: сегодняшний
    день ещё не засчитан, пользователь должен выполнить норму чтобы
    продлить дальше. Это осознанный выбор — restore не "прощает" будущее,
    он только закрывает прошлый пропуск.

    Один заряд закрывает весь текущий эпизод потери, независимо от числа
    пропущенных дней подряд. Пользователь мог болеть или быть без связи —
    несправедливо было бы списывать по заряду за каждый день.
    """
    today = local_today(tz_name)

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

    return {
        "ok": True,
        "restored_to": restored_to,
        "restores_remaining": user.streak_restores_available,
    }
