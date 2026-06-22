"""Tests for the tips endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from datetime import date
from decimal import Decimal

from db import AiTip
from tests.conftest import FAKE_TG_USER_ID


@pytest.mark.asyncio
async def test_today_tip_no_food(client: AsyncClient, seeded_user):
    """GET /api/tips/today returns message when no food logged."""
    resp = await client.get("/api/tips/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tip"] is None
    assert "Добавь" in data["message"]


@pytest.mark.asyncio
@patch("api.tips.generate_daily_tip", new_callable=AsyncMock)
async def test_today_tip_generates(
    mock_gen, client: AsyncClient, seeded_user_with_food
):
    """GET /api/tips/today generates a tip when food exists."""
    mock_gen.return_value = {
        "tip": "Отличный баланс белков сегодня!",
        "tip_type": "macro_balance",
        "icon": "🥗",
    }

    resp = await client.get("/api/tips/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tip_text"] == "Отличный баланс белков сегодня!"
    assert data["tip_type"] == "macro_balance"


@pytest.mark.asyncio
async def test_today_tip_cached(client: AsyncClient, seeded_user):
    """GET /api/tips/today returns existing tip without regenerating."""
    await AiTip.create(
        user_id=FAKE_TG_USER_ID,
        tip_text="Кешированный совет",
        tip_type="general",
        icon="💡",
        based_on_date=date.today(),
    )

    resp = await client.get("/api/tips/today")
    assert resp.status_code == 200
    assert resp.json()["tip_text"] == "Кешированный совет"


@pytest.mark.asyncio
async def test_recent_tips(client: AsyncClient, seeded_user):
    """GET /api/tips returns recent tips with pagination."""
    for i in range(5):
        await AiTip.create(
            user_id=FAKE_TG_USER_ID,
            tip_text=f"Совет {i}",
            tip_type="general",
            icon="💡",
            based_on_date=date(2026, 6, i + 1),
        )

    resp = await client.get("/api/tips?limit=3&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    resp = await client.get("/api/tips?limit=3&offset=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_recent_tips_empty(client: AsyncClient, seeded_user):
    """GET /api/tips returns empty list when no tips."""
    resp = await client.get("/api/tips")
    assert resp.status_code == 200
    assert resp.json() == []
