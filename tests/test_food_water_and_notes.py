"""Tests for AI-detected hydration auto-logging and the optional notes field."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from api.utils import _rate_limits


@pytest.fixture(autouse=True)
def clear_rate_limits():
    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.mark.asyncio
async def test_create_food_log_auto_logs_water(client: AsyncClient, seeded_user):
    """A water_ml > 0 on the food log payload auto-creates a WaterLog entry."""
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Кофе с молоком",
                    "portion_g": 250,
                    "calories": 40,
                    "protein_g": 1.5,
                    "fat_g": 1.5,
                    "carbs_g": 4.0,
                }
            ],
            "water_ml": 240,
        },
    )
    assert resp.status_code == 200

    resp = await client.get("/api/water/2026-06-12")
    assert resp.status_code == 200
    assert resp.json()["total_ml"] == 240


@pytest.mark.asyncio
async def test_create_food_log_without_water_skips_water_log(
    client: AsyncClient, seeded_user
):
    """No water_ml (or 0/null) means no WaterLog gets created."""
    await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Рис",
                    "portion_g": 150,
                    "calories": 195,
                    "protein_g": 4.1,
                    "fat_g": 0.5,
                    "carbs_g": 43.0,
                }
            ],
        },
    )

    resp = await client.get("/api/water/2026-06-12")
    assert resp.json()["total_ml"] == 0


@pytest.mark.asyncio
@patch("api.food.analyze_food_photo", new_callable=AsyncMock)
@patch("api.food.upload_food_photo", new_callable=AsyncMock)
async def test_analyze_forwards_user_notes(
    mock_upload, mock_analyze, client: AsyncClient, seeded_user
):
    """A `notes` form field is forwarded to the AI analyzer as a keyword arg."""
    mock_analyze.return_value = {
        "dishes": [],
        "total": {
            "calories": 0,
            "protein_g": 0,
            "fat_g": 0,
            "carbs_g": 0,
            "fiber_g": 0,
            "sugar_g": 0,
            "water_ml": 0,
        },
        "portion_note": "",
        "ask_user": False,
    }
    mock_upload.return_value = "food/123/abc.jpg"

    await client.post(
        "/api/food/analyze",
        files={
            "file": ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")
        },
        data={"notes": "без сахара"},
    )

    assert mock_analyze.call_args.kwargs["notes"] == "без сахара"


@pytest.mark.asyncio
@patch("api.food.analyze_food_photo", new_callable=AsyncMock)
@patch("api.food.upload_food_photo", new_callable=AsyncMock)
async def test_analyze_without_notes_passes_none(
    mock_upload, mock_analyze, client: AsyncClient, seeded_user
):
    """Omitting `notes` forwards None rather than an empty string."""
    mock_analyze.return_value = {
        "dishes": [],
        "total": {
            "calories": 0,
            "protein_g": 0,
            "fat_g": 0,
            "carbs_g": 0,
            "fiber_g": 0,
            "sugar_g": 0,
            "water_ml": 0,
        },
        "portion_note": "",
        "ask_user": False,
    }
    mock_upload.return_value = "food/123/abc.jpg"

    await client.post(
        "/api/food/analyze",
        files={
            "file": ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")
        },
    )

    assert mock_analyze.call_args.kwargs["notes"] is None
