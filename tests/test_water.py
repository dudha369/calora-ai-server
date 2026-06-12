"""Tests for the water tracking endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_water(client: AsyncClient, seeded_user):
    """POST /api/water creates a water log entry."""
    resp = await client.post("/api/water", json={
        "log_date": "2026-06-12",
        "amount_ml": 250,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount_ml"] == 250


@pytest.mark.asyncio
async def test_get_water_by_date(client: AsyncClient, seeded_user):
    """GET /api/water/{date} returns all water logs and total."""
    # Add two entries
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 250})
    await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 500})

    resp = await client.get("/api/water/2026-06-12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_ml"] == 750
    assert len(data["logs"]) == 2


@pytest.mark.asyncio
async def test_get_water_empty_date(client: AsyncClient, seeded_user):
    """GET /api/water/{date} returns empty for a date with no logs."""
    resp = await client.get("/api/water/2026-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_ml"] == 0
    assert data["logs"] == []


@pytest.mark.asyncio
async def test_delete_water(client: AsyncClient, seeded_user):
    """DELETE /api/water/{id} removes the entry."""
    # Create
    resp = await client.post("/api/water", json={"log_date": "2026-06-12", "amount_ml": 300})
    log_id = resp.json()["id"]

    # Delete
    resp = await client.delete(f"/api/water/{log_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify gone
    resp = await client.get("/api/water/2026-06-12")
    assert resp.json()["total_ml"] == 0


@pytest.mark.asyncio
async def test_delete_water_not_found(client: AsyncClient, seeded_user):
    """DELETE /api/water/{id} returns 404 for non-existent log."""
    resp = await client.delete("/api/water/99999")
    assert resp.status_code == 404
