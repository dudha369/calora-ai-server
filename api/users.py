"""
GET    /api/users/me — текущий пользователь + профиль + цели (всё в одном запросе).
DELETE /api/users/me — полное удаление аккаунта (необратимо).
"""

from fastapi import APIRouter, Depends
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
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

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
async def get_me(auth_data: WebAppInitData = Depends(auth)):
    tg_user = auth_data.user
    user = await get_or_create_user(
        telegram_id=tg_user.id,
        full_name=tg_user.first_name or "Unknown",
        username=tg_user.username,
        language_code=tg_user.language_code or "en",
    )

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

    user_data = (await UserSchema.from_tortoise_orm(user)).model_dump()

    return {
        "user": user_data,
        "profile": profile_data,
        "goal": goal_data,
        "needs_onboarding": needs_onboarding,
        "onboarding_step": onboarding_step,
    }


@router.delete("/me")
async def delete_account(auth_data: WebAppInitData = Depends(auth)):
    """
    Полностью удаляет аккаунт пользователя.

    1. Собирает ключи всех фото еды из FoodLog.photo_url и удаляет их из B2 —
       внешнее хранилище не входит в транзакцию БД, поэтому чистим его первым,
       пока ключи ещё доступны.
    2. Удаляет строку User. ON DELETE CASCADE на всех связанных таблицах
       (user_profiles, daily_goals, weight_history, food_logs → food_items,
       water_logs, quests, ai_tips, onboarding_drafts) каскадно удаляет
       абсолютно все данные пользователя одной транзакцией.

    После этого следующий GET /api/users/me пересоздаст User через
    get_or_create_user — пользователь снова попадёт на онбординг.
    """
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )

    photo_keys = await FoodLog.filter(
        user_id=user.telegram_id, photo_url__isnull=False
    ).values_list("photo_url", flat=True)

    await delete_food_photos(list(photo_keys))

    await User.filter(telegram_id=user.telegram_id).delete()

    return {"ok": True}
