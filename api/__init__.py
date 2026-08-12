from fastapi import APIRouter
from . import (
    admin,
    common,
    users,
    profile,
    onboarding,
    food,
    water,
    weight,
    quests,
    tips,
    stats,
    favorites,
    openfoodfacts,
)


def setup_routers() -> APIRouter:
    router = APIRouter()

    router.include_router(common.router)
    router.include_router(admin.router)
    router.include_router(users.router)
    router.include_router(profile.router)
    router.include_router(onboarding.router)
    router.include_router(food.router)
    router.include_router(water.router)
    router.include_router(weight.router)
    router.include_router(quests.router)
    router.include_router(tips.router)
    router.include_router(stats.router)
    router.include_router(favorites.router)
    router.include_router(openfoodfacts.router)

    return router
