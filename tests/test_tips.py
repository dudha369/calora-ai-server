"""Tests for the AI tips endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from datetime import date
from decimal import Decimal

from tests.conftest import FAKE_TG_USER_ID


@pytest.mark.asyncio
async def test_get_today_tip_no_food(client: AsyncClient, seeded_user):
    """When no food is logged today, tip returns a prompt to add food."""
    resp = await client.get("/api/tips/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tip"] is None
    assert "message" in data


@pytest.mark.asyncio
@patch("api.tips.generate_daily_tip", new_callable=AsyncMock)
async def test_get_today_tip_with_food(mock_gen, client: AsyncClient, seeded_user):
    """When food is logged, a tip gets generated and cached."""
    mock_gen.return_value = {
        "tip": "Отличный баланс белка сегодня! 💪",
        "tip_type": "macro_balance",
        "icon": "💪",
    }

    # Log some food first
    await client.post("/api/food/log", json={
        "log_date": date.today().isoformat(),
        "items": [{
            "food_name": "Тест",
            "portion_g": 200,
            "calories": 400,
            "protein_g": 30,
            "fat_g": 15,
            "carbs_g": 40,
        }],
    })

    resp = await client.get("/api/tips/today")
    assert resp.status_code == 200
    data = resp.json()
    assert "💪" in data["tip_text"] or "баланс" in data["tip_text"]

    # Second call should return cached tip (no extra AI call)
    mock_gen.reset_mock()
    resp2 = await client.get("/api/tips/today")
    assert resp2.status_code == 200
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_get_recent_tips_empty(client: AsyncClient, seeded_user):
    """GET /api/tips returns empty list when no tips exist."""
    resp = await client.get("/api/tips")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_recent_tips(client: AsyncClient, seeded_user):
    """GET /api/tips returns previously generated tips."""
    from db import AiTip

    await AiTip.create(
        user_id=FAKE_TG_USER_ID,
        tip_text="Пей больше воды!",
        tip_type="hydration",
        icon="💧",
        based_on_date=date(2026, 6, 11),
    )
    await AiTip.create(
        user_id=FAKE_TG_USER_ID,
        tip_text="Хороший баланс макросов!",
        tip_type="macro_balance",
        icon="🥗",
        based_on_date=date(2026, 6, 10),
    )

    resp = await client.get("/api/tips")
    assert resp.status_code == 200
    tips = resp.json()
    assert len(tips) == 2
