"""Tests for the weight history endpoint."""

import pytest
from httpx import AsyncClient
from decimal import Decimal

from db import WeightHistory
from tests.conftest import FAKE_TG_USER_ID


@pytest.mark.asyncio
async def test_get_weight_history(client: AsyncClient, seeded_user):
    """GET /api/weight returns weight records."""
    resp = await client.get("/api/weight")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert float(data[0]["weight_kg"]) == 80.0


@pytest.mark.asyncio
async def test_get_weight_history_multiple(client: AsyncClient, seeded_user):
    """GET /api/weight returns multiple records in order."""
    await WeightHistory.create(user_id=FAKE_TG_USER_ID, weight_kg=Decimal("79.5"))
    await WeightHistory.create(user_id=FAKE_TG_USER_ID, weight_kg=Decimal("79.0"))

    resp = await client.get("/api/weight")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_get_weight_history_pagination(client: AsyncClient, seeded_user):
    """GET /api/weight supports limit and offset."""
    for i in range(5):
        await WeightHistory.create(
            user_id=FAKE_TG_USER_ID,
            weight_kg=Decimal(f"{79 - i}.0"),
        )

    # Total: 1 (from seeded) + 5 = 6
    resp = await client.get("/api/weight?limit=3&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    resp = await client.get("/api/weight?limit=3&offset=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    resp = await client.get("/api/weight?limit=3&offset=6")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_get_weight_empty(client: AsyncClient):
    """GET /api/weight returns empty list for new user."""
    resp = await client.get("/api/weight")
    assert resp.status_code == 200
    assert resp.json() == []
