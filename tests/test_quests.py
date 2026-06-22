"""Tests for the quests endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from api.utils import _rate_limits
from db import Quest
from tests.conftest import FAKE_TG_USER_ID


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limit state between tests."""
    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.mark.asyncio
async def test_get_active_quests_empty(client: AsyncClient, seeded_user):
    """GET /api/quests returns empty list when no quests."""
    resp = await client.get("/api/quests")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_active_quests(client: AsyncClient, seeded_user):
    """GET /api/quests returns active quests."""
    await Quest.create(
        user_id=FAKE_TG_USER_ID,
        quest_key="protein_goal",
        title="Белковая неделя",
        description="Достигни цели по белку 5 дней из 7",
        icon="💪",
        target_value=Decimal("5.0"),
        current_value=Decimal("2.0"),
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )

    resp = await client.get("/api/quests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["quest_key"] == "protein_goal"


@pytest.mark.asyncio
@patch("api.quests.generate_weekly_quests", new_callable=AsyncMock)
async def test_generate_quests(mock_gen, client: AsyncClient, seeded_user):
    """POST /api/quests/generate creates quests via AI."""
    mock_gen.return_value = [
        {
            "quest_key": "hydration",
            "title": "Водный баланс",
            "description": "Пей 2л воды 5 дней",
            "icon": "💧",
            "target_value": 5,
        },
        {
            "quest_key": "streak",
            "title": "Серия",
            "description": "Поддерживай серию 3 дня",
            "icon": "🔥",
            "target_value": 3,
        },
        {
            "quest_key": "photo_log",
            "title": "Фотограф",
            "description": "Сфотографируй 5 приёмов пищи",
            "icon": "📸",
            "target_value": 5,
        },
    ]

    resp = await client.post("/api/quests/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["quests"]) == 3
    assert data["quests"][0]["quest_key"] == "hydration"


@pytest.mark.asyncio
@patch("api.quests.generate_weekly_quests", new_callable=AsyncMock)
async def test_generate_quests_too_many_active(
    mock_gen, client: AsyncClient, seeded_user
):
    """POST /api/quests/generate returns 409 when too many active quests."""
    # Create 6 active quests (MAX_ACTIVE_QUESTS)
    for i in range(6):
        await Quest.create(
            user_id=FAKE_TG_USER_ID,
            quest_key=f"quest_{i}",
            title=f"Квест {i}",
            description=f"Описание {i}",
            icon="🎯",
            target_value=Decimal("5.0"),
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

    resp = await client.post("/api/quests/generate")
    assert resp.status_code == 409
    assert "active quests" in resp.json()["detail"].lower()
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_expire_quests(client: AsyncClient, seeded_user):
    """POST /api/quests/expire marks expired quests as failed."""
    # Create an expired quest
    await Quest.create(
        user_id=FAKE_TG_USER_ID,
        quest_key="old_quest",
        title="Старый квест",
        description="Уже просрочен",
        icon="⏰",
        target_value=Decimal("5.0"),
        status="active",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    # Create a non-expired quest
    await Quest.create(
        user_id=FAKE_TG_USER_ID,
        quest_key="fresh_quest",
        title="Свежий квест",
        description="Ещё активен",
        icon="🎯",
        target_value=Decimal("3.0"),
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=5),
    )

    resp = await client.post("/api/quests/expire")
    assert resp.status_code == 200
    assert resp.json()["expired_count"] == 1

    # Verify: 1 active, 1 failed
    active = await Quest.filter(user_id=FAKE_TG_USER_ID, status="active").count()
    failed = await Quest.filter(user_id=FAKE_TG_USER_ID, status="failed").count()
    assert active == 1
    assert failed == 1


@pytest.mark.asyncio
async def test_expire_quests_none_expired(client: AsyncClient, seeded_user):
    """POST /api/quests/expire returns 0 when nothing expired."""
    resp = await client.post("/api/quests/expire")
    assert resp.status_code == 200
    assert resp.json()["expired_count"] == 0
