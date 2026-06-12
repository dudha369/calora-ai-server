"""Tests for the weight history endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_weight_history(client: AsyncClient, seeded_user):
    """GET /api/weight returns the initial weight entry from profile creation."""
    resp = await client.get("/api/weight")
    assert resp.status_code == 200

    data = resp.json()
    assert len(data) >= 1
    # The seeded user has weight_kg = 80.0
    assert any(
        float(record["weight_kg"]) == 80.0
        for record in data
    )


@pytest.mark.asyncio
async def test_get_weight_empty(client: AsyncClient):
    """GET /api/weight returns empty list for a user without records."""
    resp = await client.get("/api/weight")
    assert resp.status_code == 200
    assert resp.json() == []
