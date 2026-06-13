"""Tests for the profile endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from tests.conftest import FAKE_TG_USER_ID

PROFILE_DATA = {
    "gender": "female",
    "age": 30,
    "height_cm": 165,
    "weight_kg": 60.0,
    "goal_type": "maintain",
    "activity_level": "light",
    "dietary_restrictions": ["Вегетарианство"],
    "medical_conditions": [],
}


@pytest.mark.asyncio
@patch("api.profile._recalculate_goals", new_callable=AsyncMock)
async def test_create_profile(mock_recalc, client: AsyncClient):
    """POST /api/profile creates a new profile."""
    from db import DailyGoal
    from decimal import Decimal

    # Mock _recalculate_goals to create a DailyGoal
    async def fake_recalc(user_id, profile):
        goal, _ = await DailyGoal.get_or_create(
            user_id=user_id,
            defaults={
                "calories": 1800,
                "protein_g": Decimal("108.0"),
                "fat_g": Decimal("60.0"),
                "carbs_g": Decimal("200.0"),
                "water_ml": 1980,
            },
        )
        return goal

    mock_recalc.side_effect = fake_recalc

    resp = await client.post("/api/profile", json=PROFILE_DATA)
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"]["gender"] == "female"
    assert data["profile"]["height_cm"] == 165
    assert data["goal"]["calories"] == 1800


@pytest.mark.asyncio
async def test_create_profile_duplicate(client: AsyncClient, seeded_user):
    """POST /api/profile returns 400 if profile already exists."""
    resp = await client.post("/api/profile", json=PROFILE_DATA)
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("api.profile._recalculate_goals", new_callable=AsyncMock)
async def test_update_profile(mock_recalc, client: AsyncClient, seeded_user):
    """PUT /api/profile updates profile and recalculates goals."""
    from db import DailyGoal

    async def fake_recalc(user_id, profile):
        goal = await DailyGoal.get(user_id=user_id)
        return goal

    mock_recalc.side_effect = fake_recalc

    updated = {**PROFILE_DATA, "weight_kg": 78.0}
    resp = await client.put("/api/profile", json=updated)
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["profile"]["weight_kg"]) == 78.0


@pytest.mark.asyncio
async def test_update_profile_not_found(client: AsyncClient):
    """PUT /api/profile returns 404 if no profile exists."""
    resp = await client.put("/api/profile", json=PROFILE_DATA)
    assert resp.status_code == 404
