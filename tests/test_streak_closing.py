"""Tests for the daily streak-closing service."""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from db import User, FoodLog, Quest
from services.daily_close import close_completed_days
from tests.conftest import FAKE_TG_USER_ID

TODAY = date(2026, 6, 15)
YESTERDAY = TODAY - timedelta(days=1)


def _patched_today():
    return patch("services.daily_close._local_today", return_value=TODAY)


async def _set_last_checked(days_before_today: int) -> None:
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        last_streak_check_date=TODAY - timedelta(days=days_before_today)
    )


@pytest.mark.asyncio
async def test_streak_increments_when_goal_met(seeded_user):
    """Калории в пределах ±10% от цели на ожидающий день увеличивают стрик."""
    await _set_last_checked(2)  # "вчера" — единственный неучтённый день
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=2050,
    )

    with _patched_today():
        summary = await close_completed_days()

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1
    assert user.max_streak == 1
    assert user.last_streak_check_date == YESTERDAY
    assert summary["processed"] == 1


@pytest.mark.asyncio
async def test_streak_resets_when_goal_missed(seeded_user):
    """День далеко за пределами допуска по калориям обрывает стрик."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=5, max_streak=5
    )
    await _set_last_checked(2)
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=600,
    )

    with _patched_today():
        summary = await close_completed_days()

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0
    assert user.max_streak == 5  # исторический максимум не уменьшается
    assert summary["streak_broken"] == 1


@pytest.mark.asyncio
async def test_day_without_food_log_breaks_streak(seeded_user):
    """Отсутствие записей еды за день — тоже невыполненная цель."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(current_streak=3)
    await _set_last_checked(2)

    with _patched_today():
        await close_completed_days()

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0


@pytest.mark.asyncio
async def test_rerun_in_same_hour_is_idempotent(seeded_user):
    """Повторный прогон в течение того же часа не задваивает инкременты."""
    await _set_last_checked(2)
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=2000
    )

    with _patched_today():
        await close_completed_days()
        await close_completed_days()

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1


@pytest.mark.asyncio
async def test_backfills_multiple_missed_days(seeded_user):
    """Простой дольше дня проигрывается день за днём, а не пропускается."""
    await _set_last_checked(3)  # два ожидающих дня: TODAY-2 и TODAY-1
    for offset in (2, 1):
        await FoodLog.create(
            user_id=FAKE_TG_USER_ID,
            log_date=TODAY - timedelta(days=offset),
            total_calories=2000,
        )

    with _patched_today():
        await close_completed_days()

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 2
    assert user.last_streak_check_date == YESTERDAY


@pytest.mark.asyncio
async def test_streak_quest_syncs_and_completes(seeded_user):
    """quest_key='streak' зеркалит current_streak и завершается по target."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(current_streak=2)
    await _set_last_checked(2)
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=2000
    )
    quest = await Quest.create(
        user_id=FAKE_TG_USER_ID,
        quest_key="streak",
        title="3 дня подряд",
        description="Держи стрик 3 дня",
        icon="🔥",
        target_value=Decimal("3.0"),
        current_value=Decimal("2.0"),
        status=Quest.STATUS_ACTIVE,
        expires_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )

    with _patched_today():
        await close_completed_days()

    await quest.refresh_from_db()
    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 3
    assert quest.current_value == 3
    assert quest.status == Quest.STATUS_DONE
    assert user.quests_completed == 1