"""
GET    /api/users/me — текущий пользователь + профиль + цели (всё в одном запросе).
DELETE /api/users/me — полное удаление аккаунта (необратимо).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
from services.streaks import (
    reconcile_streak,
    is_streak_active_today,
    get_today_progress,
    restore_streak,
    decline_streak_restore,
    describe_restore_state,
    get_week_history,
    MAX_RESTORES_PER_MONTH,
)

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
            await reconcile_streak(user, profile.timezone, goal, profile.goal_type)
        except Exception:
            logger.exception("streak reconcile failed for user %s", user.telegram_id)

    user_data = (await UserSchema.from_tortoise_orm(user)).model_dump()
    user_data["streak_active_today"] = (
        is_streak_active_today(user, profile.timezone) if profile else False
    )

    return {
        "user": user_data,
        "profile": profile_data,
        "goal": goal_data,
        "needs_onboarding": needs_onboarding,
        "onboarding_step": onboarding_step,
    }


class LanguageIn(BaseModel):
    language_code: str = Field(min_length=2, max_length=8)


@router.patch("/language")
async def update_language(body: LanguageIn, user: User = Depends(get_current_user)):
    """
    Сохраняет явный выбор языка пользователя в приложении.

    Намеренно отделено от автоматического language_code в
    get_or_create_user (который отражает язык *устройства* в Telegram,
    а не то, что пользователь выбрал в приложении — см. api/utils.py).
    Используется для рассылок / будущих уведомлений на нужном языке;
    источник истины для самого UI остаётся CloudStorage.
    """
    await User.filter(telegram_id=user.telegram_id).update(
        language_code=body.language_code
    )
    return {"ok": True}


@router.get("/streak")
async def get_streak(user: User = Depends(get_current_user)):
    """
    GET /api/users/streak — данные для попапа серии на HomePage.
    Отдельный эндпоинт, а не часть /me: вызывается только по тапу
    на огонёк, не нужно тащить при каждом открытии приложения.
    """
    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    goal = await DailyGoal.get_or_none(user_id=user.telegram_id)

    if not profile or not goal:
        return {
            "current_streak": user.current_streak,
            "max_streak": user.max_streak,
            "streak_active_today": False,
            "streak_restores_available": user.streak_restores_available,
            "max_restores_per_month": MAX_RESTORES_PER_MONTH,
            **describe_restore_state(user),
            "today_progress": None,
            "goal_type": None,
            "week_history": [],
        }

    try:
        await reconcile_streak(user, profile.timezone, goal, profile.goal_type)
    except Exception:
        logger.exception("streak reconcile failed for user %s", user.telegram_id)

    today_progress = await get_today_progress(
        user.telegram_id, profile.timezone, goal, profile.goal_type
    )
    week_history = await get_week_history(user.telegram_id, profile.timezone)

    return {
        "current_streak": user.current_streak,
        "max_streak": user.max_streak,
        "streak_active_today": is_streak_active_today(user, profile.timezone),
        "streak_restores_available": user.streak_restores_available,
        "max_restores_per_month": MAX_RESTORES_PER_MONTH,
        **describe_restore_state(user),
        "today_progress": today_progress,
        "goal_type": profile.goal_type,
        "week_history": week_history,
    }


@router.post("/streak/restore")
async def restore_user_streak(user: User = Depends(get_current_user)):
    """
    POST /api/users/streak/restore — ручное восстановление серии.
    400 — нечего восстанавливать (streak_before_break is None).
    409 — нет зарядов (streak_restores_available == 0).
    410 — 48-часовое окно восстановления истекло.
    """
    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Profile not found. Complete onboarding first.",
        )

    result = await restore_streak(user, profile.timezone)

    if not result["ok"]:
        code = {
            "no_restores_available": 409,
            "restore_window_expired": 410,
        }.get(result["reason"], 400)
        raise HTTPException(status_code=code, detail=result["reason"])

    return result


@router.post("/streak/decline")
async def decline_user_streak_restore(user: User = Depends(get_current_user)):
    """
    POST /api/users/streak/decline — отказ от восстановления сгоревшей
    серии. В отличие от /restore ничего не тратит: просто закрывает текущий
    эпизод потери, разрешая начать новую серию с чистого листа.
    400 — нечего отклонять (уже закрыто/не было обрыва).
    """
    result = await decline_streak_restore(user)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return result


@router.delete("/me")
async def delete_account(user: User = Depends(get_current_user)):
    is_admin = config.ADMIN_TELEGRAM_ID and user.telegram_id == config.ADMIN_TELEGRAM_ID

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
