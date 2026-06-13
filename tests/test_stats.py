"""Tests for the stats endpoints."""

import pytest
from datetime import date
from decimal import Decimal
from httpx import AsyncClient

from db import FoodLog, FoodItem, WaterLog
from tests.conftest import FAKE_TG_USER_ID


@pytest.mark.asyncio
async def test_daily_stats_empty(client: AsyncClient, seeded_user):
    """GET /api/stats/daily returns zeros for empty day."""
    resp = await client.get("/api/stats/daily?date=2026-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calories"] == 0
    assert data["water_ml"] == 0
    assert data["has_data"] is False
    # Goals should come from seeded user
    assert data["calories_goal"] == 2000
    assert data["water_goal_ml"] == 2640


@pytest.mark.asyncio
async def test_daily_stats_invalid_date(client: AsyncClient, seeded_user):
    """GET /api/stats/daily returns 422 for invalid date."""
    resp = await client.get("/api/stats/daily?date=nope")
    assert resp.status_code == 422
    assert "Invalid date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_daily_stats_with_data(client: AsyncClient, seeded_user):
    """GET /api/stats/daily aggregates food and water."""
    d = "2026-06-12"
    # Add food
    await client.post("/api/food/log", json={
        "log_date": d,
        "items": [{"food_name": "Тест", "portion_g": 100, "calories": 300,
                    "protein_g": 20, "fat_g": 10, "carbs_g": 30}],
    })
    # Add water
    await client.post("/api/water", json={"log_date": d, "amount_ml": 500})

    resp = await client.get(f"/api/stats/daily?date={d}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calories"] == 300
    assert data["water_ml"] == 500
    assert data["has_data"] is True


@pytest.mark.asyncio
async def test_daily_stats_no_goals(client: AsyncClient):
    """GET /api/stats/daily returns zero goals for user without profile."""
    resp = await client.get("/api/stats/daily?date=2026-06-12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calories_goal"] == 0
    assert data["water_goal_ml"] == 0


@pytest.mark.asyncio
async def test_active_dates(client: AsyncClient, seeded_user):
    """GET /api/stats/active-dates returns dates with data."""
    await client.post("/api/food/log", json={
        "log_date": "2026-06-10",
        "items": [{"food_name": "A", "portion_g": 100, "calories": 100,
                    "protein_g": 5, "fat_g": 3, "carbs_g": 10}],
    })
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 250})

    resp = await client.get("/api/stats/active-dates?from=2026-06-01&to=2026-06-30")
    assert resp.status_code == 200
    dates = resp.json()["dates"]
    assert "2026-06-10" in dates
    assert "2026-06-12" in dates
    assert "2026-06-11" not in dates


@pytest.mark.asyncio
async def test_active_dates_invalid_date(client: AsyncClient, seeded_user):
    """GET /api/stats/active-dates returns 422 for invalid date."""
    resp = await client.get("/api/stats/active-dates?from=bad&to=2026-06-30")
    assert resp.status_code == 422
    assert "Invalid date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_active_dates_empty_range(client: AsyncClient, seeded_user):
    """GET /api/stats/active-dates returns empty for empty range."""
    resp = await client.get("/api/stats/active-dates?from=2020-01-01&to=2020-01-31")
    assert resp.status_code == 200
    assert resp.json()["dates"] == []
