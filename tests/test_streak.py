"""Tests for the event-driven streak logic (services/streaks.py)."""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from httpx import AsyncClient

from db import User, FoodLog, Quest, DailyGoal
from services.streaks import (
    reconcile_streak,
    sync_today_credit_state,
    restore_streak,
    decline_streak_restore,
    describe_restore_state,
    MAX_RESTORES_PER_MONTH,
)
from tests.conftest import FAKE_TG_USER_ID

TODAY = date(2026, 6, 15)
YESTERDAY = TODAY - timedelta(days=1)


def _patched_today():
    return patch("services.streaks.local_today", return_value=TODAY)


async def _set_last_checked(d: date) -> None:
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(last_streak_check_date=d)


async def _user_and_goal():
    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    goal = await DailyGoal.get(user_id=FAKE_TG_USER_ID)
    return user, goal


# ─── reconcile_streak ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_breaks_streak_after_missed_day(seeded_user):
    """Пропущенный день обрывает серию и сохраняет доразрывное значение."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=4, max_streak=4
    )
    await _set_last_checked(TODAY - timedelta(days=2))

    user, goal = await _user_and_goal()
    with _patched_today():
        changed = await reconcile_streak(user, "Europe/Kyiv", goal, "lose")

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert changed is True
    assert user.current_streak == 0
    assert user.max_streak == 4  # рекорд не уменьшается
    assert user.streak_before_break == 4  # сохранено для restore


@pytest.mark.asyncio
async def test_reconcile_saves_streak_before_break_only_on_first_miss(seeded_user):
    """Три пропущенных дня подряд: streak_before_break = значение ДО первого."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(current_streak=7)
    await _set_last_checked(TODAY - timedelta(days=4))  # 3 пропущенных дня

    user, goal = await _user_and_goal()
    with _patched_today():
        await reconcile_streak(user, "Europe/Kyiv", goal, "lose")

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0
    assert user.streak_before_break == 7


@pytest.mark.asyncio
async def test_reconcile_clears_streak_before_break_on_recovery(seeded_user):
    """Met-день внутри backfill-окна закрывает старый эпизод потери."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0, streak_before_break=5
    )
    await _set_last_checked(TODAY - timedelta(days=2))
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=2000
    )

    user, goal = await _user_and_goal()
    with _patched_today():
        await reconcile_streak(user, "Europe/Kyiv", goal, "lose")

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1
    assert user.streak_before_break is None  # эпизод закрыт, restore невозможен


@pytest.mark.asyncio
async def test_reconcile_is_noop_when_already_checked_today(seeded_user):
    """Быстрый путь: если сегодня уже проверяли — ни одного запроса к БД."""
    await _set_last_checked(TODAY)

    user, goal = await _user_and_goal()
    with _patched_today():
        changed = await reconcile_streak(user, "Europe/Kyiv", goal, "lose")

    assert changed is False


@pytest.mark.asyncio
async def test_reconcile_catches_up_multiple_days(seeded_user):
    """Backfill проигрывает все пропущенные дни по одному."""
    await _set_last_checked(TODAY - timedelta(days=3))
    for offset in (2, 1):
        await FoodLog.create(
            user_id=FAKE_TG_USER_ID,
            log_date=TODAY - timedelta(days=offset),
            total_calories=2000,
        )

    user, goal = await _user_and_goal()
    with _patched_today():
        await reconcile_streak(user, "Europe/Kyiv", goal, "lose")

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 2
    assert user.last_streak_check_date == YESTERDAY


# ─── sync_today_credit_state ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_credits_when_goal_met(seeded_user):
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000)

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1
    assert user.last_streak_check_date == TODAY


@pytest.mark.asyncio
async def test_sync_reverts_when_goal_no_longer_met(seeded_user):
    """Удаление записи до нормы откатывает кредит."""
    await _set_last_checked(YESTERDAY)
    log = await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000
    )

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 1

        await log.delete()
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0
    assert user.last_streak_check_date == YESTERDAY


@pytest.mark.asyncio
async def test_sync_is_idempotent(seeded_user):
    """Несколько food/log за день не задваивают инкремент."""
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000)

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1


@pytest.mark.asyncio
async def test_sync_credits_after_overeating_correction(seeded_user):
    """
    Переел → удалил лишнее → вернулся в норму → кредит выдаётся.
    Кейс, который не работал с раздельными credit/uncredit функциями.
    """
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1500)
    log_extra = await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1000
    )  # итого 2500 — over (цель 2000, допуск до 2200)

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 0  # over — кредита нет

        await log_extra.delete()  # осталось 1500 — below
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 0  # всё ещё below

        await FoodLog.create(
            user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=500
        )
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 1


@pytest.mark.asyncio
async def test_sync_clears_streak_before_break_on_credit(seeded_user):
    """Начало новой серии закрывает старый restore-эпизод."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(streak_before_break=10)
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000)

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.streak_before_break is None


@pytest.mark.asyncio
async def test_sync_ignores_backdated_log(seeded_user):
    """Запись задним числом не продлевает стрик через sync — это работа reconcile."""
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(
        user_id=FAKE_TG_USER_ID, log_date=YESTERDAY, total_calories=2000
    )

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", YESTERDAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0


# ─── Restore charges lifecycle ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restores_always_reset_on_new_streak_start(seeded_user):
    """Новая серия всегда даёт полный комплект — неважно сколько щитов осталось."""
    for leftover in (0, 1, 2):
        # Сбрасываем состояние между итерациями
        await FoodLog.filter(user_id=FAKE_TG_USER_ID).delete()
        await User.filter(telegram_id=FAKE_TG_USER_ID).update(
            current_streak=0,
            streak_restores_available=leftover,
            last_streak_check_date=YESTERDAY,
        )
        await FoodLog.create(
            user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000
        )

        user, goal = await _user_and_goal()
        with _patched_today():
            await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 1
        assert user.streak_restores_available == MAX_RESTORES_PER_MONTH, (
            f"leftover={leftover}: expected {MAX_RESTORES_PER_MONTH}, "
            f"got {user.streak_restores_available}"
        )


@pytest.mark.asyncio
async def test_restores_not_reset_when_extending_active_streak(seeded_user):
    """Продление существующей серии не трогает щиты."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=5,
        streak_restores_available=1,
    )
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000)

    user, goal = await _user_and_goal()
    with _patched_today():
        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 6
    assert user.streak_restores_available == 1  # щиты не тронуты


# ─── restore_streak ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_succeeds(seeded_user):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=8,
        streak_restores_available=2,
    )

    user, _ = await _user_and_goal()
    with _patched_today():
        result = await restore_streak(user, "Europe/Kyiv")

    assert result["ok"] is True
    assert result["restored_to"] == 8
    assert result["restores_remaining"] == 1

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 8
    assert user.streak_before_break is None
    assert user.streak_restores_available == 1
    assert user.last_streak_check_date == YESTERDAY  # сегодня ещё не засчитано


@pytest.mark.asyncio
async def test_restore_fails_when_no_break(seeded_user):
    """Нельзя восстановить то, что не сломано."""
    user, _ = await _user_and_goal()
    with _patched_today():
        result = await restore_streak(user, "Europe/Kyiv")

    assert result["ok"] is False
    assert result["reason"] == "no_break_to_restore"


@pytest.mark.asyncio
async def test_restore_fails_when_no_charges(seeded_user):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=5,
        streak_restores_available=0,
    )

    user, _ = await _user_and_goal()
    with _patched_today():
        result = await restore_streak(user, "Europe/Kyiv")

    assert result["ok"] is False
    assert result["reason"] == "no_restores_available"


@pytest.mark.asyncio
async def test_restore_then_continue_streak(seeded_user):
    """После restore пользователь должен выполнить норму сегодня чтобы продолжить."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=5,
        streak_restores_available=2,
    )
    await _set_last_checked(YESTERDAY - timedelta(days=1))
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=2000)

    user, goal = await _user_and_goal()
    with _patched_today():
        await restore_streak(user, "Europe/Kyiv")
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        assert user.current_streak == 5
        assert user.last_streak_check_date == YESTERDAY  # сегодня ещё не засчитано

        await sync_today_credit_state(user, goal, "Europe/Kyiv", TODAY)

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 6
    assert user.last_streak_check_date == TODAY


@pytest.mark.asyncio
async def test_restore_cannot_be_used_twice_on_same_break(seeded_user):
    """Второй restore после первого невозможен — streak_before_break уже None."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=5,
        streak_restores_available=2,
    )

    user, _ = await _user_and_goal()
    with _patched_today():
        r1 = await restore_streak(user, "Europe/Kyiv")
        user = await User.get(telegram_id=FAKE_TG_USER_ID)
        r2 = await restore_streak(user, "Europe/Kyiv")

    assert r1["ok"] is True
    assert r2["ok"] is False
    assert r2["reason"] == "no_break_to_restore"


@pytest.mark.asyncio
async def test_quest_completes_on_restore(seeded_user):
    """Quest 'streak' с target=5 завершается когда restore возвращает к 5."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=5,
        streak_restores_available=2,
    )
    quest = await Quest.create(
        user_id=FAKE_TG_USER_ID,
        quest_key="streak",
        title="5 дней",
        description="",
        icon="🔥",
        target_value=Decimal("5.0"),
        current_value=Decimal("0.0"),
        status=Quest.STATUS_ACTIVE,
        expires_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )

    user, _ = await _user_and_goal()
    with _patched_today():
        await restore_streak(user, "Europe/Kyiv")

    await quest.refresh_from_db()
    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert quest.status == Quest.STATUS_DONE
    assert user.quests_completed == 1


# ─── End-to-end HTTP ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_food_log_credits_streak_e2e(client: AsyncClient, seeded_user):
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
    assert me.json()["user"]["streak_active_today"] is True


@pytest.mark.asyncio
async def test_food_delete_reverts_streak_e2e(client: AsyncClient, seeded_user):
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

        await client.delete(f"/api/food/{log_id}")
        me = await client.get("/api/users/me")

    assert me.json()["user"]["current_streak"] == 0
    assert me.json()["user"]["streak_active_today"] is False


@pytest.mark.asyncio
async def test_get_streak_endpoint(client: AsyncClient, seeded_user):
    await _set_last_checked(YESTERDAY)
    await FoodLog.create(user_id=FAKE_TG_USER_ID, log_date=TODAY, total_calories=1000)

    with _patched_today():
        resp = await client.get("/api/users/streak")

    assert resp.status_code == 200
    data = resp.json()
    assert data["current_streak"] == 0
    assert data["streak_active_today"] is False
    assert data["streak_restores_available"] == MAX_RESTORES_PER_MONTH
    assert data["can_restore"] is False
    assert data["today_progress"]["status"] == "below"
    assert data["today_progress"]["calories"] == 1000
    # min = 2000 - 10% = 1800, remaining = 1800 - 1000 = 800
    assert data["today_progress"]["calories_remaining"] == 800


@pytest.mark.asyncio
async def test_restore_endpoint_succeeds(client: AsyncClient, seeded_user):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=5,
        streak_restores_available=2,
    )

    with _patched_today():
        resp = await client.post("/api/users/streak/restore")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["restored_to"] == 5
    assert data["restores_remaining"] == 1


@pytest.mark.asyncio
async def test_restore_endpoint_returns_400_when_no_break(
    client: AsyncClient, seeded_user
):
    with _patched_today():
        resp = await client.post("/api/users/streak/restore")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_restore_endpoint_returns_409_when_no_charges(
    client: AsyncClient, seeded_user
):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=5,
        streak_restores_available=0,
    )
    with _patched_today():
        resp = await client.post("/api/users/streak/restore")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_streak_endpoint_shows_can_restore_after_break(
    client: AsyncClient, seeded_user
):
    """GET /api/users/streak отдаёт can_restore=True если серия сломана и есть заряды."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=7,
        streak_restores_available=2,
    )

    with _patched_today():
        resp = await client.get("/api/users/streak")

    assert resp.status_code == 200
    assert resp.json()["can_restore"] is True


# ─── Restore window expiry & decline ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_fails_after_window_expires(seeded_user):
    """Щит нельзя потратить, если 48 часов с момента обрыва уже прошли."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=6,
        streak_broken_at=datetime.now(timezone.utc) - timedelta(hours=49),
        streak_restores_available=2,
    )

    user, _ = await _user_and_goal()
    result = await restore_streak(user, "Europe/Kyiv")

    assert result["ok"] is False
    assert result["reason"] == "restore_window_expired"

    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.current_streak == 0
    assert user.streak_before_break == 6  # щит не потрачен, эпизод не закрыт


@pytest.mark.asyncio
async def test_restore_succeeds_just_before_window_expires(seeded_user):
    """На 47-м часу восстановление всё ещё доступно."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=6,
        streak_broken_at=datetime.now(timezone.utc) - timedelta(hours=47),
        streak_restores_available=2,
    )

    user, _ = await _user_and_goal()
    result = await restore_streak(user, "Europe/Kyiv")

    assert result["ok"] is True
    assert result["restored_to"] == 6


def test_describe_restore_state_reflects_expiry():
    """Чистая функция describe_restore_state не трогает БД и корректно
    считает can_restore/restore_expired по одним только полям User."""
    user = User(
        telegram_id=1,
        full_name="X",
        streak_before_break=3,
        streak_broken_at=datetime.now(timezone.utc) - timedelta(hours=50),
        streak_restores_available=1,
    )
    state = describe_restore_state(user)
    assert state["can_restore"] is False
    assert state["restore_expired"] is True
    assert state["lost_streak_value"] == 3


@pytest.mark.asyncio
async def test_decline_streak_restore_clears_break(seeded_user):
    """Отказ от восстановления закрывает эпизод без траты щита."""
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=4,
        streak_broken_at=datetime.now(timezone.utc) - timedelta(hours=1),
        streak_restores_available=3,
    )

    user, _ = await _user_and_goal()
    result = await decline_streak_restore(user)

    assert result["ok"] is True
    user = await User.get(telegram_id=FAKE_TG_USER_ID)
    assert user.streak_before_break is None
    assert user.streak_broken_at is None
    assert user.streak_restores_available == 3  # щит не потрачен


@pytest.mark.asyncio
async def test_decline_streak_restore_endpoint(client: AsyncClient, seeded_user):
    await User.filter(telegram_id=FAKE_TG_USER_ID).update(
        current_streak=0,
        streak_before_break=4,
        streak_broken_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    resp = await client.post("/api/users/streak/decline")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = await client.get("/api/users/streak")
    data = resp.json()
    assert data["lost_streak_value"] is None
    assert data["can_restore"] is False
