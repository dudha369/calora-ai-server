"""Tests for the stats endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_daily_stats_empty(client: AsyncClient, seeded_user):
    """GET /api/stats/daily returns zeroes when no food/water logged."""
    resp = await client.get("/api/stats/daily", params={"date": "2026-06-12"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["calories"] == 0
    assert data["protein_g"] == 0
    assert data["water_ml"] == 0
    assert data["has_data"] is False
    # Goals should come from the seeded DailyGoal
    assert data["calories_goal"] == 2000
    assert data["water_goal_ml"] == 2640


@pytest.mark.asyncio
async def test_daily_stats_with_water(client: AsyncClient, seeded_user):
    """Stats reflect water logs for the queried date."""
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 500})
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 300})

    resp = await client.get("/api/stats/daily", params={"date": "2026-06-12"})
    data = resp.json()
    assert data["water_ml"] == 800
    assert data["has_data"] is True


@pytest.mark.asyncio
async def test_active_dates_empty(client: AsyncClient, seeded_user):
    """GET /api/stats/active-dates returns empty list when nothing logged."""
    resp = await client.get("/api/stats/active-dates", params={
        "from": "2026-06-01",
        "to": "2026-06-30",
    })
    assert resp.status_code == 200
    assert resp.json()["dates"] == []


@pytest.mark.asyncio
async def test_active_dates_with_water(client: AsyncClient, seeded_user):
    """Active dates include days with water logs."""
    await client.post("/api/water", json={"log_date": "2026-06-10", "amount_ml": 250})
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 500})

    resp = await client.get("/api/stats/active-dates", params={
        "from": "2026-06-01",
        "to": "2026-06-30",
    })
    dates = resp.json()["dates"]
    assert "2026-06-10" in dates
    assert "2026-06-12" in dates
    assert len(dates) == 2


@pytest.mark.asyncio
async def test_daily_stats_no_profile(client: AsyncClient):
    """Stats for a user without a profile return zero goals."""
    resp = await client.get("/api/stats/daily", params={"date": "2026-06-12"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["calories_goal"] == 0
    assert data["water_goal_ml"] == 0
