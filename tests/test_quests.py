"""Tests for the quests endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from db import Quest
from tests.conftest import FAKE_TG_USER_ID


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
