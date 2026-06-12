"""Tests for the onboarding flow."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_onboarding_progress_empty(client: AsyncClient):
    """Fresh user has no onboarding progress → step 1."""
    resp = await client.get("/api/onboarding/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["step"] == 1
    assert data["data"] == {}


@pytest.mark.asyncio
async def test_save_step(client: AsyncClient):
    """POST /api/onboarding/step saves draft data."""
    # Step 1: gender
    resp = await client.post("/api/onboarding/step", json={
        "step": 2,
        "gender": "male",
    })
    assert resp.status_code == 200

    # Verify via progress
    resp = await client.get("/api/onboarding/progress")
    data = resp.json()
    assert data["step"] == 2
    assert data["data"]["gender"] == "male"


@pytest.mark.asyncio
async def test_save_multiple_steps(client: AsyncClient):
    """Multiple step saves accumulate data in the draft."""
    await client.post("/api/onboarding/step", json={"step": 2, "gender": "female"})
    await client.post("/api/onboarding/step", json={"step": 3, "age": 30})
    await client.post("/api/onboarding/step", json={"step": 4, "height": 165})

    resp = await client.get("/api/onboarding/progress")
    data = resp.json()
    assert data["step"] == 4
    assert data["data"]["gender"] == "female"
    assert data["data"]["age"] == 30
    assert data["data"]["height"] == 165


@pytest.mark.asyncio
async def test_complete_onboarding_missing_fields(client: AsyncClient):
    """Complete fails if required fields are missing."""
    # Only save gender — missing age, height, weight, etc.
    await client.post("/api/onboarding/step", json={"step": 2, "gender": "male"})

    resp = await client.post("/api/onboarding/complete")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_complete_onboarding_no_draft(client: AsyncClient):
    """Complete fails if there's no draft at all."""
    resp = await client.post("/api/onboarding/complete")
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("api.onboarding._recalculate_goals", new_callable=AsyncMock)
async def test_complete_onboarding_success(mock_recalc, client: AsyncClient):
    """Full onboarding flow → profile + goals created."""
    from db import DailyGoal
    from decimal import Decimal

    # Save all required steps
    await client.post("/api/onboarding/step", json={"step": 2, "gender": "male"})
    await client.post("/api/onboarding/step", json={"step": 3, "age": 25})
    await client.post("/api/onboarding/step", json={"step": 4, "height": 180})
    await client.post("/api/onboarding/step", json={"step": 5, "weight": 80.0})
    await client.post("/api/onboarding/step", json={"step": 6, "goal": "lose"})
    await client.post("/api/onboarding/step", json={"step": 7, "target_weight": 75.0})
    await client.post("/api/onboarding/step", json={"step": 8, "activity_level": 1.55})
    await client.post("/api/onboarding/step", json={
        "step": 9,
        "dietary_restrictions": [],
    })
    await client.post("/api/onboarding/step", json={
        "step": 10,
        "water_track": "auto",
    })
    await client.post("/api/onboarding/step", json={
        "step": 11,
        "medical_conditions": [],
    })

    # Mock will raise to trigger the fallback path
    mock_recalc.side_effect = Exception("AI unavailable")

    resp = await client.post("/api/onboarding/complete")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # User should no longer need onboarding
    resp = await client.get("/api/users/me")
    data = resp.json()
    assert data["needs_onboarding"] is False
    assert data["profile"]["gender"] == "male"
    assert data["profile"]["height_cm"] == 180


@pytest.mark.asyncio
async def test_reset_onboarding(client: AsyncClient, seeded_user):
    """DELETE /api/onboarding/reset clears profile and goals."""
    # Confirm profile exists
    resp = await client.get("/api/users/me")
    assert resp.json()["needs_onboarding"] is False

    # Reset
    resp = await client.delete("/api/onboarding/reset")
    assert resp.status_code == 200

    # Now needs onboarding again
    resp = await client.get("/api/users/me")
    assert resp.json()["needs_onboarding"] is True
