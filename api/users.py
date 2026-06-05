"""
GET /api/users/me — текущий пользователь + профиль + цели (всё в одном запросе).
Вызывается при каждом открытии Mini App.
"""

from fastapi import APIRouter, Depends
from aiogram.utils.web_app import WebAppInitData
from tortoise.exceptions import DoesNotExist

from .utils import auth, get_or_create_user
from db import UserSchema, UserProfileSchema, DailyGoalSchema, OnboardingDraft

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
async def get_me(auth_data: WebAppInitData = Depends(auth)):
    tg_user = auth_data.user
    user = await get_or_create_user(
        tg_id=tg_user.id,
        full_name=tg_user.first_name or "Unknown",
        username=tg_user.username,
        language_code=tg_user.language_code or "en",
    )

    try:
        profile = await user.profile
        profile_data = (await UserProfileSchema.from_tortoise_orm(profile)).model_dump()
    except DoesNotExist:
        profile_data = None

    try:
        goal = await user.daily_goal
        goal_data = (await DailyGoalSchema.from_tortoise_orm(goal)).model_dump()
    except DoesNotExist:
        goal_data = None

    needs_onboarding = profile_data is None

    onboarding_step = 0
    if needs_onboarding:
        draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
        if draft:
            onboarding_step = draft.step

    user_data = (await UserSchema.from_tortoise_orm(user)).model_dump()

    return {
        "user": user_data,
        "profile": profile_data,
        "goal": goal_data,
        "needs_onboarding": needs_onboarding,
        "onboarding_step": onboarding_step,
    }
