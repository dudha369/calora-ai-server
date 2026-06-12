"""Tests for GET /api/users/me."""

import pytest
from httpx import AsyncClient

from tests.conftest import FAKE_TG_USER_ID


@pytest.mark.asyncio
async def test_get_me_new_user(client: AsyncClient):
    """A brand-new user gets auto-created and needs onboarding."""
    resp = await client.get("/api/users/me")
    assert resp.status_code == 200

    data = resp.json()
    assert data["needs_onboarding"] is True
    assert data["profile"] is None
    assert data["goal"] is None
    assert data["user"]["telegram_id"] == FAKE_TG_USER_ID
    assert data["user"]["full_name"] == "Test"


@pytest.mark.asyncio
async def test_get_me_with_profile(client: AsyncClient, seeded_user):
    """A user with a completed profile gets full data back."""
    resp = await client.get("/api/users/me")
    assert resp.status_code == 200

    data = resp.json()
    assert data["needs_onboarding"] is False
    assert data["profile"] is not None
    assert data["goal"] is not None
    assert data["goal"]["calories"] == 2000
    assert data["profile"]["gender"] == "male"
    assert data["profile"]["height_cm"] == 180
