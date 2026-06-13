"""
POST /api/profile — создать профиль напрямую (без онбординга, для тестов/админки)
PUT  /api/profile — обновить профиль
Оба эндпоинта пересчитывают DailyGoal через goal_calculator.

_recalculate_goals — внутренняя функция, импортируется также из api/onboarding.py.
"""

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .utils import get_current_user
from db import User, UserProfile, UserProfileSchema, DailyGoal, WeightHistory
from ai.services.goal_calculator import calculate_and_personalize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileIn(BaseModel):
    gender: str
    age: int
    height_cm: int
    weight_kg: float
    goal_type: str
    activity_level: str  # 'sedentary' | 'light' | 'moderate' | 'active' | 'extreme'
    target_weight_kg: Optional[float] = None
    water_track: str = "auto"  # 'auto' | 'manual' | 'none'
    water_goal_ml: Optional[int] = None
    dietary_restrictions: list[str] = []
    allergy_note: Optional[str] = None
    medical_conditions: list[str] = []


async def _recalculate_goals(user_id: int, profile: UserProfile) -> DailyGoal:
    """Пересчитывает DailyGoal по данным профиля (формула + Gemini)."""
    profile_data = {
        "gender": profile.gender,
        "age": profile.age,
        "height_cm": profile.height_cm,
        "weight_kg": float(profile.weight_kg),
        "goal_type": profile.goal_type,
        "activity_level": profile.activity_level,
        "dietary_restrictions": profile.dietary_restrictions,
        "medical_conditions": profile.medical_conditions,
    }
    goals = await calculate_and_personalize(profile_data)

    goal, _ = await DailyGoal.get_or_create(user_id=user_id)
    await DailyGoal.filter(user_id=user_id).update(
        calories=goals["calories"],
        protein_g=goals["protein_g"],
        fat_g=goals["fat_g"],
        carbs_g=goals["carbs_g"],
        water_ml=goals["water_ml"],
        ai_tip=goals.get("ai_tip"),
    )
    await goal.refresh_from_db()
    return goal


@router.post("")
async def create_profile(body: ProfileIn, user: User = Depends(get_current_user)):
    """Создаёт профиль напрямую (минуя онбординг). Если уже есть — 400."""
    if await UserProfile.get_or_none(user_id=user.telegram_id):
        raise HTTPException(status_code=400, detail="Profile already exists. Use PUT.")

    profile = await UserProfile.create(
        user_id=user.telegram_id,
        gender=body.gender,
        age=body.age,
        height_cm=body.height_cm,
        weight_kg=Decimal(str(body.weight_kg)),
        goal_type=body.goal_type,
        target_weight_kg=(
            Decimal(str(body.target_weight_kg)) if body.target_weight_kg else None
        ),
        activity_level=body.activity_level,
        water_track=body.water_track,
        water_goal_ml=body.water_goal_ml,
        dietary_restrictions=body.dietary_restrictions,
        allergy_note=body.allergy_note,
        medical_conditions=body.medical_conditions,
    )

    await WeightHistory.create(user_id=user.telegram_id, weight_kg=profile.weight_kg)
    goal = await _recalculate_goals(user.telegram_id, profile)

    return {
        "profile": (await UserProfileSchema.from_tortoise_orm(profile)).model_dump(),
        "goal": {
            "calories": goal.calories,
            "protein_g": float(goal.protein_g),
            "fat_g": float(goal.fat_g),
            "carbs_g": float(goal.carbs_g),
            "water_ml": goal.water_ml,
            "ai_tip": goal.ai_tip,
        },
    }


@router.put("")
async def update_profile(body: ProfileIn, user: User = Depends(get_current_user)):
    """Обновляет профиль и пересчитывает DailyGoal."""
    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Use POST.")

    old_weight = profile.weight_kg
    new_weight = Decimal(str(body.weight_kg))

    await UserProfile.filter(user_id=user.telegram_id).update(
        gender=body.gender,
        age=body.age,
        height_cm=body.height_cm,
        weight_kg=new_weight,
        goal_type=body.goal_type,
        target_weight_kg=(
            Decimal(str(body.target_weight_kg)) if body.target_weight_kg else None
        ),
        activity_level=body.activity_level,
        water_track=body.water_track,
        water_goal_ml=body.water_goal_ml,
        dietary_restrictions=body.dietary_restrictions,
        allergy_note=body.allergy_note,
        medical_conditions=body.medical_conditions,
    )
    await profile.refresh_from_db()

    if old_weight != new_weight:
        await WeightHistory.create(user_id=user.telegram_id, weight_kg=new_weight)

    goal = await _recalculate_goals(user.telegram_id, profile)

    return {
        "profile": (await UserProfileSchema.from_tortoise_orm(profile)).model_dump(),
        "goal": {
            "calories": goal.calories,
            "protein_g": float(goal.protein_g),
            "fat_g": float(goal.fat_g),
            "carbs_g": float(goal.carbs_g),
            "water_ml": goal.water_ml,
            "ai_tip": goal.ai_tip,
        },
    }
