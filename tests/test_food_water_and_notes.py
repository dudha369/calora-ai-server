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


@pytest.mark.asyncio
async def test_delete_food_log_removes_auto_water(client: AsyncClient, seeded_user):
    """Удаление food log удаляет автоматически созданную воду, но не ручную."""
    log_date = "2026-06-15"

    # Логируем еду с водой (например, кофе)
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": log_date,
            "items": [
                {
                    "food_name": "Кофе",
                    "portion_g": 200,
                    "calories": 5,
                    "protein_g": 0.3,
                    "fat_g": 0.1,
                    "carbs_g": 0.8,
                    "water_ml": 196,
                }
            ],
            # water_ml суммируется из items на бэкенде
        },
    )
    assert resp.status_code == 200
    log_id = resp.json()["log"]["id"]

    # Добавляем ручную воду — она должна остаться после удаления еды
    await client.post("/api/water", json={"log_date": log_date, "amount_ml": 300})

    # Проверяем что вода есть: 196 (авто) + 300 (ручная) = 496
    water = await client.get(f"/api/water/{log_date}")
    assert water.json()["total_ml"] == 496

    # Удаляем food log
    resp = await client.delete(f"/api/food/{log_id}")
    assert resp.status_code == 200

    # Авто-вода (196 мл) должна исчезнуть, ручная (300 мл) остаётся
    water = await client.get(f"/api/water/{log_date}")
    assert water.json()["total_ml"] == 300


@pytest.mark.asyncio
async def test_repeat_food_log_copies_water(client: AsyncClient, seeded_user):
    """Повторение food log с напитками корректно добавляет воду."""
    log_date_original = "2026-06-14"
    log_date_today = "2026-06-15"

    # Создаём оригинальную запись с кофе (water_ml=196 per item)
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": log_date_original,
            "items": [
                {
                    "food_name": "Американо",
                    "portion_g": 200,
                    "calories": 5,
                    "protein_g": 0.3,
                    "fat_g": 0.1,
                    "carbs_g": 0.8,
                    "water_ml": 196,
                }
            ],
        },
    )
    original_log_id = resp.json()["log"]["id"]

    # Имитируем repeat: берём items из оригинала и логируем на сегодня
    # (в реальном приложении это делает food.repeat() на фронтенде)
    resp = await client.post(
        "/api/food/log",
        json={
            "log_date": log_date_today,
            "items": [
                {
                    "food_name": "Американо",
                    "portion_g": 200,
                    "calories": 5,
                    "protein_g": 0.3,
                    "fat_g": 0.1,
                    "carbs_g": 0.8,
                    "water_ml": 196,
                }
            ],
            # Нет явного water_ml на уровне лога — бэкенд суммирует из items
        },
    )
    assert resp.status_code == 200
    repeated_log_id = resp.json()["log"]["id"]

    # Вода должна появиться на сегодня
    water = await client.get(f"/api/water/{log_date_today}")
    assert water.json()["total_ml"] == 196

    # Удаляем повторённую запись — вода тоже должна исчезнуть
    await client.delete(f"/api/food/{repeated_log_id}")
    water = await client.get(f"/api/water/{log_date_today}")
    assert water.json()["total_ml"] == 0
