"""Tests for the water logging endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_water(client: AsyncClient, seeded_user):
    """POST /api/water creates a water log."""
    resp = await client.post("/api/water", json={
        "log_date": "2026-06-12",
        "amount_ml": 250,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount_ml"] == 250


@pytest.mark.asyncio
async def test_add_water_invalid_date(client: AsyncClient, seeded_user):
    """POST /api/water returns 422 for invalid date."""
    resp = await client.post("/api/water", json={
        "log_date": "garbage",
        "amount_ml": 250,
    })
    assert resp.status_code == 422
    assert "Invalid date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_water_by_date(client: AsyncClient, seeded_user):
    """GET /api/water/{date} returns all logs for that date."""
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 250})
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 500})

    resp = await client.get("/api/water/2026-06-12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-06-12"
    assert len(data["logs"]) == 2
    assert data["total_ml"] == 750


@pytest.mark.asyncio
async def test_get_water_invalid_date(client: AsyncClient, seeded_user):
    """GET /api/water/{date} returns 422 for invalid date."""
    resp = await client.get("/api/water/nope")
    assert resp.status_code == 422
    assert "Invalid date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_water_empty_date(client: AsyncClient, seeded_user):
    """GET /api/water/{date} returns empty for a date with no logs."""
    resp = await client.get("/api/water/2026-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logs"] == []
    assert data["total_ml"] == 0


@pytest.mark.asyncio
async def test_delete_water(client: AsyncClient, seeded_user):
    """DELETE /api/water/{log_id} removes the log."""
    resp = await client.post("/api/water", json={
        "log_date": "2026-06-12",
        "amount_ml": 300,
    })
    log_id = resp.json()["id"]

    resp = await client.delete(f"/api/water/{log_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify deleted
    resp = await client.get("/api/water/2026-06-12")
    assert len(resp.json()["logs"]) == 0


@pytest.mark.asyncio
async def test_delete_water_not_found(client: AsyncClient, seeded_user):
    """DELETE /api/water/{log_id} returns 404 for non-existent log."""
    resp = await client.delete("/api/water/99999")
    assert resp.status_code == 404
