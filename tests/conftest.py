"""
Shared fixtures for the Calora AI test suite.

Uses an in-memory SQLite database so tests run without PostgreSQL.
Tortoise ORM is initialised once per test and schemas are
re-created before every test function to guarantee isolation.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

# Ensure we don't load .env secrets (set dummy values before importing app)
os.environ.setdefault("BOT_TOKEN", "0000000000:AAFakeTokenForTesting")
os.environ.setdefault("DB_URL", "sqlite://:memory:")
os.environ.setdefault("WEBHOOK_URL", "https://test.example.com")
os.environ.setdefault("WEBAPP_URL", "https://test.example.com")
os.environ.setdefault("GEMINI_API_KEY", "fake-key")

# ── Tortoise test config (SQLite in-memory) ─────────────────────────────────

TORTOISE_TEST_CONFIG = {
    "connections": {"default": "sqlite://:memory:"},
    "apps": {
        "models": {
            "models": [
                "db.models.user",
                "db.models.user_profile",
                "db.models.onboarding_draft",
                "db.models.daily_goal",
                "db.models.weight_history",
                "db.models.food_log",
                "db.models.food_item",
                "db.models.water_log",
                "db.models.quest",
                "db.models.ai_tip",
            ],
            "default_connection": "default",
        }
    },
}

# ── Event loop ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Database lifecycle ───────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def init_db():
    """Initialise Tortoise with SQLite and recreate schemas before each test."""
    await Tortoise.init(TORTOISE_TEST_CONFIG)
    await Tortoise.generate_schemas()
    yield
    await Tortoise._drop_databases()
    await Tortoise.close_connections()


# ── Fake Telegram initData auth ──────────────────────────────────────────────

FAKE_TG_USER_ID = 123456789
FAKE_TG_FIRST_NAME = "Test"
FAKE_TG_USERNAME = "testuser"


class FakeWebAppUser:
    """Minimal stub that satisfies auth() expectations."""
    id = FAKE_TG_USER_ID
    first_name = FAKE_TG_FIRST_NAME
    username = FAKE_TG_USERNAME
    language_code = "en"


class FakeWebAppInitData:
    user = FakeWebAppUser()


def _fake_auth(_request=None):
    """Replace the real auth dependency with one that always succeeds."""
    return FakeWebAppInitData()


# ── Async HTTP client (via HTTPX) ───────────────────────────────────────────

# Build the FastAPI app once with a no-op lifespan
_app_built = False


def _get_test_app():
    """Build the test app exactly once (idempotent)."""
    global _app_built
    from fastapi import FastAPI
    from api.utils import auth as real_auth
    from api import setup_routers as setup_api_routers

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    app = FastAPI(lifespan=_noop_lifespan)
    app.include_router(setup_api_routers())
    app.dependency_overrides[real_auth] = _fake_auth
    _app_built = True
    return app


_test_app = None


@pytest_asyncio.fixture
async def client():
    """
    Yields an ``httpx.AsyncClient`` wired to the FastAPI app.

    - Uses a no-op lifespan (no webhook, no production Tortoise init).
    - Patches ``auth`` so no real Telegram initData is needed.
    - Tortoise is managed by the ``init_db`` fixture above.
    """
    global _test_app
    if _test_app is None:
        _test_app = _get_test_app()

    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helper: seed a complete user (profile + goals) ──────────────────────────

@pytest_asyncio.fixture
async def seeded_user(client: AsyncClient):
    """
    Creates a user with a full profile and daily goals directly in the DB.
    Returns the User model instance.
    """
    from db import User, UserProfile, DailyGoal, WeightHistory

    # Create user
    user = await User.create(
        telegram_id=FAKE_TG_USER_ID,
        full_name=FAKE_TG_FIRST_NAME,
        username=FAKE_TG_USERNAME,
        language_code="en",
    )

    # Create profile
    await UserProfile.create(
        user_id=user.telegram_id,
        gender="male",
        age=25,
        height_cm=180,
        weight_kg=Decimal("80.0"),
        goal_type="lose",
        activity_level="moderate",
        water_track="auto",
        dietary_restrictions=[],
        medical_conditions=[],
    )

    # Create daily goals
    await DailyGoal.create(
        user_id=user.telegram_id,
        calories=2000,
        protein_g=Decimal("144.0"),
        fat_g=Decimal("66.7"),
        carbs_g=Decimal("200.0"),
        water_ml=2640,
    )

    # Create initial weight history
    await WeightHistory.create(
        user_id=user.telegram_id,
        weight_kg=Decimal("80.0"),
    )

    return user


@pytest_asyncio.fixture
async def seeded_user_with_food(seeded_user):
    """
    Seeded user + food log for today.
    Returns the User model instance.
    """
    from db import FoodLog, FoodItem

    food_log = await FoodLog.create(
        user_id=seeded_user.telegram_id,
        log_date=date.today(),
        total_calories=500,
        total_protein_g=Decimal("30.0"),
        total_fat_g=Decimal("15.0"),
        total_carbs_g=Decimal("50.0"),
    )

    await FoodItem.create(
        food_log_id=food_log.id,
        food_name="Тестовое блюдо",
        portion_g=Decimal("300.0"),
        calories=500,
        protein_g=Decimal("30.0"),
        fat_g=Decimal("15.0"),
        carbs_g=Decimal("50.0"),
    )

    return seeded_user
