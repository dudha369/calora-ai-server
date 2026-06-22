"""
GET  /api/onboarding/progress  — текущий шаг + данные черновика
POST /api/onboarding/step      — сохранить данные шага
POST /api/onboarding/complete  — завершить онбординг → профиль + цели
DELETE /api/onboarding/reset   — сбросить профиль/цели → заново на онбординг
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .utils import get_current_user, parse_date
from .profile import _recalculate_goals
from db import User, OnboardingDraft, UserProfile, DailyGoal, WeightHistory
from ai.services.goal_calculator import calculate_base_goals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

ACTIVITY_MAP: dict[float, str] = {
    1.2: "sedentary",
    1.375: "light",
    1.55: "moderate",
    1.725: "active",
    1.9: "extreme",
}
ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "extreme": 1.9,
}


class StepDataIn(BaseModel):
    step: int
    gender: Optional[str] = None
    birth_date: Optional[str] = None  # "YYYY-MM-DD"
    height: Optional[int] = None
    weight: Optional[float] = None
    goal: Optional[str] = None
    target_weight: Optional[float] = None
    activity_level: Optional[float] = None
    dietary_restrictions: Optional[list[str]] = None
    allergy_note: Optional[str] = None
    water_track: Optional[str] = None
    water_goal: Optional[int] = None
    medical_conditions: Optional[list[str]] = None
    timezone: Optional[str] = None


def _draft_to_response(draft: OnboardingDraft) -> dict:
    return {
        "gender": draft.gender,
        "birth_date": draft.birth_date.isoformat() if draft.birth_date else None,
        "height": draft.height_cm,
        "weight": float(draft.weight_kg) if draft.weight_kg else None,
        "goal": draft.goal,
        "target_weight": float(draft.target_weight) if draft.target_weight else None,
        "activity_level": draft.activity_level,
        "dietary_restrictions": draft.dietary_restrictions,
        "allergy_note": draft.allergy_note,
        "water_track": draft.water_track,
        "water_goal": draft.water_goal_ml,
        "medical_conditions": draft.medical_conditions,
        "timezone": draft.timezone,
    }


@router.get("/progress")
async def get_progress(user: User = Depends(get_current_user)):
    draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
    if not draft:
        return {"step": 1, "data": {}}
    return {"step": draft.step, "data": _draft_to_response(draft)}


@router.post("/step")
async def save_step(body: StepDataIn, user: User = Depends(get_current_user)):
    draft, _ = await OnboardingDraft.get_or_create(user_id=user.telegram_id)
    update: dict = {"step": body.step}

    if body.gender is not None:
        update["gender"] = body.gender
    if body.birth_date is not None:
        update["birth_date"] = parse_date(body.birth_date)
    if body.height is not None:
        update["height_cm"] = body.height
    if body.weight is not None:
        update["weight_kg"] = Decimal(str(body.weight))
    if body.goal is not None:
        update["goal"] = body.goal
    if body.target_weight is not None:
        update["target_weight"] = Decimal(str(round(body.target_weight, 1)))
    if body.activity_level is not None:
        update["activity_level"] = body.activity_level
    if body.dietary_restrictions is not None:
        update["dietary_restrictions"] = body.dietary_restrictions
    if body.allergy_note is not None:
        update["allergy_note"] = body.allergy_note
    if body.water_track is not None:
        update["water_track"] = body.water_track
    if body.water_goal is not None:
        update["water_goal_ml"] = body.water_goal
    if body.medical_conditions is not None:
        update["medical_conditions"] = body.medical_conditions
    if body.timezone is not None:
        update["timezone"] = body.timezone

    await OnboardingDraft.filter(user_id=user.telegram_id).update(**update)
    return {"ok": True}


@router.post("/complete")
async def complete_onboarding(user: User = Depends(get_current_user)):
    draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
    if not draft:
        raise HTTPException(status_code=400, detail="No onboarding draft found")

    missing = [
        k
        for k, v in {
            "gender": draft.gender,
            "birth_date": draft.birth_date,
            "height_cm": draft.height_cm,
            "weight_kg": draft.weight_kg,
            "goal": draft.goal,
            "activity_level": draft.activity_level,
            "water_track": draft.water_track,
        }.items()
        if v is None
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Onboarding incomplete. Missing: {', '.join(missing)}",
        )

    activity_str = ACTIVITY_MAP.get(draft.activity_level, "moderate")
    water_goal_ml = draft.water_goal_ml if draft.water_track == "manual" else None

    profile_data = dict(
        gender=draft.gender,
        birth_date=draft.birth_date,
        height_cm=draft.height_cm,
        weight_kg=float(draft.weight_kg),
        goal_type=draft.goal,
        activity_level=activity_str,
        dietary_restrictions=draft.dietary_restrictions,
        medical_conditions=draft.medical_conditions,
        target_weight_kg=draft.target_weight,
        water_track=draft.water_track,
        water_goal_ml=water_goal_ml,
        allergy_note=draft.allergy_note,
        timezone=draft.timezone or "Europe/Kyiv",
    )

    existing = await UserProfile.get_or_none(user_id=user.telegram_id)
    if existing:
        await UserProfile.filter(user_id=user.telegram_id).update(**profile_data)
        profile = await UserProfile.get(user_id=user.telegram_id)
    else:
        profile = await UserProfile.create(user_id=user.telegram_id, **profile_data)
        await WeightHistory.create(
            user_id=user.telegram_id,
            weight_kg=profile.weight_kg,
            log_date=date.today(),
        )

    # Черновик удаляем ДО вызова AI — пользователь уже "завершил" онбординг
    # даже если Gemini упадёт, при следующем открытии приложения он попадёт в главный экран
    await draft.delete()

    try:
        await _recalculate_goals(user.telegram_id, profile)
    except Exception as e:
        logger.error(f"AI goal calculation failed for user {user.telegram_id}: {e}")
        # Fallback: Mifflin-St Jeor без AI
        goals = calculate_base_goals(
            {
                "gender": profile.gender,
                "birth_date": profile.birth_date,
                "height_cm": profile.height_cm,
                "weight_kg": float(profile.weight_kg),
                "goal_type": profile.goal_type,
                "activity_level": profile.activity_level,
            }
        )
        goal, _ = await DailyGoal.get_or_create(
            user_id=user.telegram_id,
            defaults={**goals, "ai_tip": None},
        )
        if goal.calories == 0:  # если запись была пустой
            await DailyGoal.filter(user_id=user.telegram_id).update(**goals)

    return {"ok": True}


@router.delete("/reset")
async def reset_onboarding(user: User = Depends(get_current_user)):
    """
    Сбрасывает профиль и цели пользователя.
    После вызова GET /api/users/me вернёт needs_onboarding=True.
    Используется для повторного прохождения онбординга.
    """
    await UserProfile.filter(user_id=user.telegram_id).delete()
    await DailyGoal.filter(user_id=user.telegram_id).delete()
    await OnboardingDraft.filter(user_id=user.telegram_id).delete()
    return {"ok": True}
