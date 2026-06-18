"""
GET    /api/users/me — текущий пользователь + профиль + цели (всё в одном запросе).
DELETE /api/users/me — полное удаление аккаунта (необратимо).
"""

import logging

from fastapi import APIRouter, Depends

from .utils import get_current_user
from db import (
    User,
    UserSchema,
    UserProfile,
    UserProfileSchema,
    DailyGoal,
    DailyGoalSchema,
    OnboardingDraft,
    FoodLog,
)
from services.storage import delete_food_photos
from services.streaks import reconcile_streak

from config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    # get_or_none надёжнее, чем user.profile — обратная связь в Tortoise
    # может вернуть None вместо DoesNotExist в зависимости от версии ORM.
    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    profile_data = (
        (await UserProfileSchema.from_tortoise_orm(profile)).model_dump()
        if profile
        else None
    )

    goal = await DailyGoal.get_or_none(user_id=user.telegram_id)
    goal_data = (
        (await DailyGoalSchema.from_tortoise_orm(goal)).model_dump() if goal else None
    )

    needs_onboarding = profile_data is None

    onboarding_step = 0
    if needs_onboarding:
        draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
        if draft:
            onboarding_step = draft.step

    # Ленивая проверка обрыва серии. В типичном случае (юзер уже заходил
    # сегодня) — одно сравнение дат без запроса к БД.
    if profile and goal:
        try:
            await reconcile_streak(user, profile.timezone, goal)
        except Exception:
            logger.exception("streak reconcile failed for user %s", user.telegram_id)

    user_data = (await UserSchema.from_tortoise_orm(user)).model_dump()

    return {
        "user": user_data,
        "profile": profile_data,
        "goal": goal_data,
        "needs_onboarding": needs_onboarding,
        "onboarding_step": onboarding_step,
    }


@router.delete("/me")
async def delete_account(user: User = Depends(get_current_user)):
    is_admin = (
        config.ADMIN_TELEGRAM_ID
        and user.telegram_id == config.ADMIN_TELEGRAM_ID
    )

    if is_admin:
        await UserProfile.filter(user_id=user.telegram_id).delete()
        await DailyGoal.filter(user_id=user.telegram_id).delete()
        await OnboardingDraft.filter(user_id=user.telegram_id).delete()

        return {"ok": True}

    photo_keys = await FoodLog.filter(
        user_id=user.telegram_id, photo_url__isnull=False
    ).values_list("photo_url", flat=True)

    await delete_food_photos(list(photo_keys))
    await User.filter(telegram_id=user.telegram_id).delete()

    return {"ok": True}
