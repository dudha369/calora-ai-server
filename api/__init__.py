from fastapi import APIRouter
from . import common, users


def setup_routers() -> APIRouter:
    router = APIRouter()

    router.include_router(common.router)
    router.include_router(users.router)

    return router
