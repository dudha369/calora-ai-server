"""Tests for the quests endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_quests_empty(client: AsyncClient, seeded_user):
    """GET /api/quests returns empty when no quests exist."""
    resp = await client.get("/api/quests")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
@patch("api.quests.generate_weekly_quests", new_callable=AsyncMock)
async def test_generate_quests(mock_gen, client: AsyncClient, seeded_user):
    """POST /api/quests/generate creates 3 quests via AI."""
    mock_gen.return_value = [
        {
            "quest_key": "protein_goal",
            "title": "Белковая неделя",
            "description": "Достигни цели по белку 5 дней из 7",
            "icon": "💪",
            "target_value": 5,
            "expires_days": 7,
        },
        {
            "quest_key": "hydration",
            "title": "Водный марафон",
            "description": "Выпивай норму воды 4 дня подряд",
            "icon": "💧",
            "target_value": 4,
            "expires_days": 7,
        },
        {
            "quest_key": "photo_log",
            "title": "Фотограф",
            "description": "Сфотографируй 10 приёмов пищи",
            "icon": "📸",
            "target_value": 10,
            "expires_days": 7,
        },
    ]

    resp = await client.post("/api/quests/generate")
    assert resp.status_code == 200

    data = resp.json()
    assert len(data["quests"]) == 3
    assert data["quests"][0]["quest_key"] == "protein_goal"
    assert data["quests"][0]["status"] == "active"
    assert float(data["quests"][0]["current_value"]) == 0

    # Verify they show up in GET
    resp = await client.get("/api/quests")
    assert len(resp.json()) == 3
