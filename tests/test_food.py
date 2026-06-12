"""Tests for the food logging endpoints."""

import pytest
from httpx import AsyncClient
from decimal import Decimal

from db import FoodLog, FoodItem


@pytest.mark.asyncio
async def test_create_food_log(client: AsyncClient, seeded_user):
    """POST /api/food/log creates a food log with items."""
    resp = await client.post("/api/food/log", json={
        "log_date": "2026-06-12",
        "items": [
            {
                "food_name": "Куриная грудка",
                "portion_g": 200,
                "calories": 330,
                "protein_g": 62.0,
                "fat_g": 7.2,
                "carbs_g": 0.0,
            },
            {
                "food_name": "Рис",
                "portion_g": 150,
                "calories": 195,
                "protein_g": 4.1,
                "fat_g": 0.5,
                "carbs_g": 43.0,
            },
        ],
    })
    assert resp.status_code == 200

    data = resp.json()
    assert data["log"]["total_calories"] == 525
    assert len(data["items"]) == 2
    assert data["items"][0]["food_name"] == "Куриная грудка"


@pytest.mark.asyncio
async def test_create_food_log_with_photo_key(client: AsyncClient, seeded_user):
    """Food log can include a photo_key from the analyze step."""
    resp = await client.post("/api/food/log", json={
        "log_date": "2026-06-12",
        "items": [{
            "food_name": "Салат",
            "portion_g": 300,
            "calories": 150,
            "protein_g": 5.0,
            "fat_g": 10.0,
            "carbs_g": 12.0,
        }],
        "photo_key": "food/123456789/abc123.jpg",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_food_by_date(client: AsyncClient, seeded_user):
    """GET /api/food/{date} returns all logs for that date."""
    # Create two logs
    await client.post("/api/food/log", json={
        "log_date": "2026-06-12",
        "items": [{"food_name": "Завтрак", "portion_g": 100, "calories": 200,
                    "protein_g": 10, "fat_g": 5, "carbs_g": 25}],
    })
    await client.post("/api/food/log", json={
        "log_date": "2026-06-12",
        "items": [{"food_name": "Обед", "portion_g": 300, "calories": 500,
                    "protein_g": 30, "fat_g": 15, "carbs_g": 50}],
    })

    resp = await client.get("/api/food/2026-06-12")
    assert resp.status_code == 200

    data = resp.json()
    assert data["date"] == "2026-06-12"
    assert len(data["logs"]) == 2
    assert data["daily_total"]["calories"] == 700


@pytest.mark.asyncio
async def test_get_food_empty_date(client: AsyncClient, seeded_user):
    """GET /api/food/{date} returns empty for a date with no logs."""
    resp = await client.get("/api/food/2026-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logs"] == []
    assert data["daily_total"]["calories"] == 0


@pytest.mark.asyncio
async def test_delete_food_log(client: AsyncClient, seeded_user):
    """DELETE /api/food/{id} removes the log and its items."""
    # Create
    resp = await client.post("/api/food/log", json={
        "log_date": "2026-06-12",
        "items": [{"food_name": "Тест", "portion_g": 100, "calories": 100,
                    "protein_g": 5, "fat_g": 3, "carbs_g": 10}],
    })
    log_id = resp.json()["log"]["id"]

    # Delete
    resp = await client.delete(f"/api/food/{log_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify deleted
    resp = await client.get("/api/food/2026-06-12")
    assert len(resp.json()["logs"]) == 0


@pytest.mark.asyncio
async def test_delete_food_log_not_found(client: AsyncClient, seeded_user):
    """DELETE /api/food/{id} returns 404 for non-existent log."""
    resp = await client.delete("/api/food/99999")
    assert resp.status_code == 404
