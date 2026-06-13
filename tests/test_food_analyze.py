"""Tests for /api/food/analyze — rate limiting, MIME validation, file size."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from api.food import _rate_limits


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limit state between tests."""
    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.mark.asyncio
@patch("api.food.analyze_food_photo", new_callable=AsyncMock)
@patch("api.food.upload_food_photo", new_callable=AsyncMock)
async def test_analyze_success(mock_upload, mock_analyze, client: AsyncClient, seeded_user):
    """POST /api/food/analyze returns analysis result."""
    mock_analyze.return_value = {
        "items": [{"food_name": "Салат", "portion_g": 200, "calories": 150,
                    "protein_g": 5, "fat_g": 8, "carbs_g": 10}]
    }
    mock_upload.return_value = "food/123/abc.jpg"

    resp = await client.post(
        "/api/food/analyze",
        files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["photo_key"] == "food/123/abc.jpg"


@pytest.mark.asyncio
async def test_analyze_invalid_mime(client: AsyncClient, seeded_user):
    """POST /api/food/analyze rejects non-image files."""
    resp = await client.post(
        "/api/food/analyze",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_analyze_file_too_large(client: AsyncClient, seeded_user):
    """POST /api/food/analyze rejects files over 10 MB."""
    big_file = b"\x00" * (11 * 1024 * 1024)  # 11 MB
    resp = await client.post(
        "/api/food/analyze",
        files={"file": ("big.jpg", big_file, "image/jpeg")},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


@pytest.mark.asyncio
@patch("api.food.analyze_food_photo", new_callable=AsyncMock)
@patch("api.food.upload_food_photo", new_callable=AsyncMock)
async def test_analyze_rate_limit(mock_upload, mock_analyze, client: AsyncClient, seeded_user):
    """POST /api/food/analyze enforces rate limiting."""
    mock_analyze.return_value = {"items": []}
    mock_upload.return_value = "food/123/abc.jpg"

    small_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    # First 5 requests should succeed
    for _ in range(5):
        resp = await client.post(
            "/api/food/analyze",
            files={"file": ("photo.jpg", small_jpeg, "image/jpeg")},
        )
        assert resp.status_code == 200

    # 6th request should be rate-limited
    resp = await client.post(
        "/api/food/analyze",
        files={"file": ("photo.jpg", small_jpeg, "image/jpeg")},
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
@patch("api.food.analyze_food_photo", new_callable=AsyncMock)
@patch("api.food.upload_food_photo", new_callable=AsyncMock)
@patch("api.food.delete_food_photo", new_callable=AsyncMock)
async def test_analyze_unrecognized_food(
    mock_delete, mock_upload, mock_analyze, client: AsyncClient, seeded_user
):
    """POST /api/food/analyze deletes photo when food is not recognized."""
    mock_analyze.return_value = {"error": "No food detected in image"}
    mock_upload.return_value = "food/123/abc.jpg"

    resp = await client.post(
        "/api/food/analyze",
        files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")},
    )
    assert resp.status_code == 422
    mock_delete.assert_called_once_with("food/123/abc.jpg")
