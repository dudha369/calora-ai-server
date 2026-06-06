from decimal import Decimal
from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
from .profile import _recalculate_goals
from db import OnboardingDraft, UserProfile, DailyGoal, WeightHistory

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


# ─── Fallback: Mifflin-St Jeor без AI ───────────────────────────────────────


def _calc_goals_local(profile: UserProfile) -> dict:
    weight = float(profile.weight_kg)
    height = profile.height_cm
    age = profile.age
    gender = profile.gender
    activity = ACTIVITY_MULTIPLIERS.get(profile.activity_level, 1.55)
    goal = profile.goal_type

    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender == "male" else -161)
    tdee = bmr * activity
    calories = int(
        tdee - 500 if goal == "lose" else tdee + 300 if goal == "gain" else tdee
    )
    protein_g = round(weight * 1.8, 1)
    fat_g = round(calories * 0.30 / 9, 1)
    carbs_g = round((calories - protein_g * 4 - fat_g * 9) / 4, 1)
    water_ml = max(int(weight * 33), 1500)
    return {
        "calories": calories,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
        "water_ml": water_ml,
    }


# ─── Schemas ────────────────────────────────────────────────────────────────


class StepDataIn(BaseModel):
    step: int
    gender: Optional[str] = None
    age: Optional[int] = None
    height: Optional[int] = None  # всегда в см
    weight: Optional[float] = None  # всегда в кг
    goal: Optional[str] = None
    target_weight: Optional[float] = None  # всегда в кг (конвертация на фронте)
    activity_level: Optional[float] = None
    dietary_restrictions: Optional[list[str]] = None
    allergy_note: Optional[str] = None
    water_track: Optional[str] = None
    water_goal: Optional[int] = None
    medical_conditions: Optional[list[str]] = None


# ─── Helpers ────────────────────────────────────────────────────────────────


def _draft_to_response(draft: OnboardingDraft) -> dict:
    return {
        "gender": draft.gender,
        "age": draft.age,
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
    }


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/progress")
async def get_progress(auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id,
        auth_data.user.first_name or "Unknown",
        auth_data.user.username,
    )
    draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
    if not draft:
        return {"step": 1, "data": {}}
    return {"step": draft.step, "data": _draft_to_response(draft)}


@router.post("/step")
async def save_step(body: StepDataIn, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id,
        auth_data.user.first_name or "Unknown",
        auth_data.user.username,
    )
    draft, _ = await OnboardingDraft.get_or_create(user_id=user.telegram_id)
    update: dict = {"step": body.step}

    if body.gender is not None:
        update["gender"] = body.gender
    if body.age is not None:
        update["age"] = body.age
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

    await OnboardingDraft.filter(user_id=user.telegram_id).update(**update)
    return {"ok": True}


@router.post("/complete")
async def complete_onboarding(auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id,
        auth_data.user.first_name or "Unknown",
        auth_data.user.username,
    )
    draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
    if not draft:
        raise HTTPException(status_code=400, detail="No onboarding draft found")

    missing = [
        k
        for k, v in {
            "gender": draft.gender,
            "age": draft.age,
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
        age=draft.age,
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
    )

    existing = await UserProfile.get_or_none(user_id=user.telegram_id)
    if existing:
        await UserProfile.filter(user_id=user.telegram_id).update(**profile_data)
        profile = await UserProfile.get(user_id=user.telegram_id)
    else:
        profile = await UserProfile.create(user_id=user.telegram_id, **profile_data)
        await WeightHistory.create(
            user_id=user.telegram_id, weight_kg=profile.weight_kg
        )

    # Черновик удаляем ДО вызова AI — пользователь уже "завершил" онбординг
    # даже если Gemini упадёт, при следующем открытии приложения он попадёт в главный экран
    await draft.delete()

    try:
        await _recalculate_goals(user.telegram_id, profile)
    except Exception as e:
        logger.error(f"AI goal calculation failed for user {user.telegram_id}: {e}")
        # Fallback: Mifflin-St Jeor без AI
        goals = _calc_goals_local(profile)
        goal, _ = await DailyGoal.get_or_create(
            user_id=user.telegram_id,
            defaults={**goals, "ai_tip": None},
        )
        if goal.calories == 0:  # если запись была пустой
            await DailyGoal.filter(user_id=user.telegram_id).update(**goals)

    return {"ok": True}


@router.delete("/reset")
async def reset_onboarding(auth_data: WebAppInitData = Depends(auth)):
    """
    DEBUG: сбрасывает онбординг — удаляет UserProfile, DailyGoal и черновик.
    После этого при следующем GET /api/users/me вернётся needs_onboarding: true.
    """
    user = await get_or_create_user(
        auth_data.user.id,
        auth_data.user.first_name or "Unknown",
        auth_data.user.username,
    )
    await UserProfile.filter(user_id=user.telegram_id).delete()
    await DailyGoal.filter(user_id=user.telegram_id).delete()
    await OnboardingDraft.filter(user_id=user.telegram_id).delete()
    return {"ok": True, "message": "Onboarding reset. Open app to start over."}
