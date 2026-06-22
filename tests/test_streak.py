"""Tests for the event-driven streak logic (services/streaks.py)."""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from httpx import AsyncClient

from db import User, FoodLog, Quest, DailyGoal
from services.streaks import (
    reconcile_streak,
    credit_today_if_goal_met,
    uncredit_today_if_goal_no_longer_met,
)
from tests.conftest import FAKE_TG_USER_ID

TODAY = date(2026, 6, 15)
YESTERDAY = TODAY - timedelta(days=1)


def _patched_today():
    return patch("services.streaks._local_today", return_value=TODAY)


async def _set_last_checked(d) -> None:
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(last_streak_check_date=d)


async def _user_and_goal():
    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    goal = await DailyGoal.get(user_id=FAKE_TG_USER_ID)
    return user, goal


@pytest.mark.asyncio
async def test_uncredit_reverts_streak_when_today_no_longer_met(seeded_user):
    """Удаление записи, из-за которой день перестал попадать в норму,
    откатывает сегодняшний кредит."""
    await _set_last_checked(YESTERDAY)
    log = await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2050
    )

    user, goal = await _user_and_goal()
    with _patched_today():
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 1

        await log.delete()
        await uncredit_today_if_goal_no_longer_met(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0
    assert user.last_streak_check_date == YESTERDAY


@pytest.mark.asyncio
async def test_uncredit_noop_when_other_logs_still_meet_goal(seeded_user):
    """Если за день есть несколько записей, удаление одной не обязательно
    ломает норму — тогда кредит не трогаем."""
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1000)
    log2 = await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1050
    )

    user, goal = await _user_and_goal()
    with _patched_today():
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 1

        await log2.delete()  # осталось 1000 — вне ±10% от 2000
        await uncredit_today_if_goal_no_longer_met(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0


@pytest.mark.asyncio
async def test_uncredit_ignores_past_day_deletion(seeded_user):
    """Удаление записи из ПРОШЛОГО дня не трогает current_streak —
    это известное ограничение, не баг."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(current_streak=5)
    await _set_last_checked(TODAY)

    user, goal = await _user_and_goal()
    with _patched_today():
        await uncredit_today_if_goal_no_longer_met(user, goal, "Europe/Kyiv", YESTERDAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 5


@pytest.mark.asyncio
async def test_food_delete_endpoint_reverts_streak_end_to_end(
    client: AsyncClient, seeded_user
):
    """Сквозная проверка: POST продлевает стрик и флаг, DELETE откатывает оба."""
    await _set_last_checked(YESTERDAY)

    with _patched_today():
        resp = await client.post(
            "/api/food/log",
            json={
                "log_date": TODAY.isoformat(),
                "items": [
                    {
                        "food_name": "Тест",
                        "portion_g": 500,
                        "calories": 2000,
                        "protein_g": 140,
                        "fat_g": 65,
                        "carbs_g": 200,
                    }
                ],
            },
        )
        log_id = resp.json()["log"]["id"]

        me = await client.get("/api/users/me")
        assert me.json()["user"]["current_streak"] == 1
        assert me.json()["user"]["streak_active_today"] is True

        await client.delete(f"/api/food/{log_id}")

        me = await client.get("/api/users/me")
        assert me.json()["user"]["current_streak"] == 0
        assert me.json()["user"]["streak_active_today"] is False


@pytest.mark.asyncio
async def test_credit_increments_streak_when_goal_met_today(seeded_user):
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2050)

    user, goal = await _user_and_goal()
    with _patched_today():
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1
    assert user.last_streak_check_date == TODAY


@pytest.mark.asyncio
async def test_credit_is_idempotent_within_same_day(seeded_user):
    """Два POST /food/log за один день не задваивают инкремент."""
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1000)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1050)

    user, goal = await _user_and_goal()
    with _patched_today():
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1


@pytest.mark.asyncio
async def test_credit_ignores_backdated_log(seeded_user):
    """Запись задним числом не продлевает стрик через credit — это работа reconcile."""
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=2000
    )

    user, goal = await _user_and_goal()
    with _patched_today():
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", YESTERDAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0


@pytest.mark.asyncio
async def test_reconcile_breaks_streak_after_missed_day(seeded_user):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=4, max_streak=4
    )
    await _set_last_checked(TODAY - timedelta(days=2))

    user, goal = await _user_and_goal()
    with _patched_today():
        changed = await reconcile_streak(user, "Europe/Kyiv", goal)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert changed is True
    assert user.current_streak == 0
    assert user.max_streak == 4


@pytest.mark.asyncio
async def test_reconcile_is_noop_when_today_already_checked(seeded_user):
    await _set_last_checked(TODAY)

    user, goal = await _user_and_goal()
    with _patched_today():
        changed = await reconcile_streak(user, "Europe/Kyiv", goal)

    assert changed is False


@pytest.mark.asyncio
async def test_reconcile_catches_up_after_downtime(seeded_user):
    await _set_last_checked(TODAY - timedelta(days=3))
    for offset in (2, 1):
        await FoodLog.create(
            user_id=FAKE_TG_USER_ID,
            log_date=TODAY - timedelta(days=offset),
            total_calories=2000,
        )

    user, goal = await _user_and_goal()
    with _patched_today():
        await reconcile_streak(user, "Europe/Kyiv", goal)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 2
    assert user.last_streak_check_date == YESTERDAY


@pytest.mark.asyncio
async def test_streak_quest_completes_via_credit(seeded_user):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(current_streak=2)
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000)
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

    user, goal = await _user_and_goal()
    with _patched_today():
        await credit_today_if_goal_met(user, goal, "Europe/Kyiv", TODAY)

    await quest.refresh_from_db()
    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 3
    assert quest.status == Quest.STATUS_DONE
    assert user.quests_completed == 1


@pytest.mark.asyncio
async def test_food_log_endpoint_credits_streak_end_to_end(
    client: AsyncClient, seeded_user
):
    """Сквозная проверка реального HTTP-пути, не только сервисной функции."""
    await _set_last_checked(YESTERDAY)

    with _patched_today():
        resp = await client.post(
            "/api/food/log",
            json={
                "log_date": TODAY.isoformat(),
                "items": [
                    {
                        "food_name": "Тест",
                        "portion_g": 500,
                        "calories": 2000,
                        "protein_g": 140,
                        "fat_g": 65,
                        "carbs_g": 200,
                    }
                ],
            },
        )
        assert resp.status_code == 200

        me = await client.get("/api/users/me")

    assert me.json()["user"]["current_streak"] == 1
