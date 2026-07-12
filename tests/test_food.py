"""Tests for the food logging endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from decimal import Decimal

from db import FoodLog, FoodItem


@pytest.mark.asyncio
async def test_create_food_log(client: AsyncClient, seeded_user):
    """POST /api/food/log creates a food log with items."""
    resp = await client.post(
        "/api/food/log",
        json={
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
        },
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["log"]["total_calories"] == 525
    assert len(data["items"]) == 2
    assert data["items"][0]["food_name"] == "Куриная грудка"


@pytest.mark.asyncio
async def test_create_food_log_with_photo_key(client: AsyncClient, seeded_user):
    """Food log can include a photo_key from the analyze step."""
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Салат",
                    "portion_g": 300,
                    "calories": 150,
                    "protein_g": 5.0,
                    "fat_g": 10.0,
                    "carbs_g": 12.0,
                }
            ],
            "photo_key": "food/123456789/abc123.jpg",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_food_log_invalid_date(client: AsyncClient, seeded_user):
    """POST /api/food/log returns 422 for invalid date."""
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": "not-a-date",
            "items": [
                {
                    "food_name": "Тест",
                    "portion_g": 100,
                    "calories": 100,
                    "protein_g": 5,
                    "fat_g": 3,
                    "carbs_g": 10,
                }
            ],
        },
    )
    assert resp.status_code == 422
    assert "Invalid date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_food_by_date(client: AsyncClient, seeded_user):
    """GET /api/food/{date} returns all logs for that date."""
    # Create two logs
    await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Завтрак",
                    "portion_g": 100,
                    "calories": 200,
                    "protein_g": 10,
                    "fat_g": 5,
                    "carbs_g": 25,
                }
            ],
        },
    )
    await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Обед",
                    "portion_g": 300,
                    "calories": 500,
                    "protein_g": 30,
                    "fat_g": 15,
                    "carbs_g": 50,
                }
            ],
        },
    )

    resp = await client.get("/api/food/2026-06-12")
    assert resp.status_code == 200

    data = resp.json()
    assert data["date"] == "2026-06-12"
    assert len(data["logs"]) == 2
    assert data["daily_total"]["calories"] == 700


@pytest.mark.asyncio
async def test_get_food_invalid_date(client: AsyncClient, seeded_user):
    """GET /api/food/{date} returns 422 for invalid date."""
    resp = await client.get("/api/food/13-2026-01")
    assert resp.status_code == 422
    assert "Invalid date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_food_empty_date(client: AsyncClient, seeded_user):
    """GET /api/food/{date} returns empty for a date with no logs."""
    resp = await client.get("/api/food/2026-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logs"] == []
    assert data["daily_total"]["calories"] == 0


@pytest.mark.asyncio
@patch("api.food.delete_food_photo", new_callable=AsyncMock)
async def test_delete_shared_photo_keeps_file_while_referenced(
    mock_del, client: AsyncClient, seeded_user
):
    """Удаление одной из двух записей с общим photo_key не трогает B2,
    пока жива вторая ссылка."""
    photo_key = "food/123456789/shared.jpg"

    async def make_log():
        resp = await client.post(
            "/api/food/log",
            json={
                "log_date": "2026-06-12",
                "items": [{
                    "food_name": "Тест", "portion_g": 100, "calories": 100,
                    "protein_g": 5, "fat_g": 3, "carbs_g": 10,
                }],
                "photo_key": photo_key,
            },
        )
        return resp.json()["log"]["id"]

    log_a = await make_log()
    log_b = await make_log()

    resp = await client.delete(f"/api/food/{log_a}")
    assert resp.status_code == 200
    mock_del.assert_not_called()  # фото ещё используется log_b

    resp = await client.delete(f"/api/food/{log_b}")
    assert resp.status_code == 200
    mock_del.assert_called_once_with(photo_key)  # последняя ссылка ушла


@pytest.mark.asyncio
async def test_delete_food_log_without_photo(client: AsyncClient, seeded_user):
    """DELETE /api/food/{id} works for logs without photos."""
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Тест",
                    "portion_g": 100,
                    "calories": 100,
                    "protein_g": 5,
                    "fat_g": 3,
                    "carbs_g": 10,
                }
            ],
        },
    )
    log_id = resp.json()["log"]["id"]

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


@pytest.mark.asyncio
@patch("api.food.delete_food_photo", new_callable=AsyncMock)
async def test_delete_orphan_photo(mock_del, client: AsyncClient, seeded_user):
    """DELETE /api/food/photo/{key} deletes an orphaned photo from B2."""
    resp = await client.delete("/api/food/photo/food/123456789/abc123def.jpg")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    mock_del.assert_called_once_with("food/123456789/abc123def.jpg")


@pytest.mark.asyncio
async def test_delete_orphan_photo_invalid_key(client: AsyncClient, seeded_user):
    """DELETE /api/food/photo/{key} rejects invalid key format."""
    resp = await client.delete("/api/food/photo/not-a-valid-key")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_orphan_photo_wrong_user(client: AsyncClient, seeded_user):
    """DELETE /api/food/photo/{key} rejects other user's photos."""
    # seeded_user has telegram_id 123456789, try deleting user 999999's photo
    resp = await client.delete("/api/food/photo/food/999999/abc123def456.jpg")
    assert resp.status_code == 403


@pytest.mark.asyncio
@patch("api.food.delete_food_photo", new_callable=AsyncMock)
async def test_delete_orphan_photo_in_use(mock_del, client: AsyncClient, seeded_user):
    """DELETE /api/food/photo/{key} rejects deletion of photo in use by a food log."""
    # Create a food log with photo
    photo_key = "food/123456789/abc123def456.jpg"
    await client.post(
        "/api/food/log",
        json={
            "log_date": "2026-06-12",
            "items": [
                {
                    "food_name": "Тест",
                    "portion_g": 100,
                    "calories": 100,
                    "protein_g": 5,
                    "fat_g": 3,
                    "carbs_g": 10,
                }
            ],
            "photo_key": photo_key,
        },
    )

    resp = await client.delete(f"/api/food/photo/{photo_key}")
    assert resp.status_code == 409
    mock_del.assert_not_called()
