"""
GET  /api/onboarding/progress  — текущий шаг и данные черновика
POST /api/onboarding/step      — сохранить данные одного шага
POST /api/onboarding/complete  — завершить онбординг: создать профиль, удалить черновик
"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
from .profile import _recalculate_goals
from db import OnboardingDraft, UserProfile, WeightHistory

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# Соответствие PAL-мультипликатора строковому ключу для goal_calculator
ACTIVITY_MAP: dict[float, str] = {
    1.2: "sedentary",
    1.375: "light",
    1.55: "moderate",
    1.725: "active",
    1.9: "extreme",
}


# ─── Schemas ────────────────────────────────────────────────────────────────


class StepDataIn(BaseModel):
    """Тело POST /api/onboarding/step. Все поля кроме step — опциональны."""

    step: int

    # Шаг 1
    gender: Optional[str] = None
    # Шаг 2
    age: Optional[int] = None
    # Шаг 3 — height всегда в см (конвертация на фронтенде)
    height: Optional[int] = None
    height_unit: Optional[str] = None
    # Шаг 4 — weight всегда в кг
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    # Шаг 5
    goal: Optional[str] = None
    # Шаг 6
    target_weight: Optional[float] = None
    # Шаг 7 — float-мультипликатор: 1.2 | 1.375 | 1.55 | 1.725 | 1.9
    activity_level: Optional[float] = None
    # Шаг 8
    dietary_restrictions: Optional[list[str]] = None
    allergy_note: Optional[str] = None
    # Шаг 9
    water_track: Optional[str] = None
    water_goal: Optional[int] = None
    # Шаг 10
    medical_conditions: Optional[list[str]] = None


# ─── Helpers ────────────────────────────────────────────────────────────────


def _draft_to_response(draft: OnboardingDraft) -> dict:
    """Сериализует черновик в формат, ожидаемый фронтендом (OnboardingData)."""
    return {
        "gender": draft.gender,
        "age": draft.age,
        "height": draft.height_cm,
        "height_unit": draft.height_unit,
        "weight": float(draft.weight_kg) if draft.weight_kg else None,
        "weight_unit": draft.weight_unit,
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
    """Возвращает текущий шаг и данные черновика. Если черновика нет — step=1, data={}."""
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
    """Сохраняет данные текущего шага в черновик. Создаёт черновик если его нет."""
    user = await get_or_create_user(
        auth_data.user.id,
        auth_data.user.first_name or "Unknown",
        auth_data.user.username,
    )

    draft, _ = await OnboardingDraft.get_or_create(user_id=user.telegram_id)

    # Обновляем только переданные поля
    update: dict = {"step": body.step}

    if body.gender is not None:
        update["gender"] = body.gender
    if body.age is not None:
        update["age"] = body.age
    if body.height is not None:
        update["height_cm"] = body.height
    if body.height_unit is not None:
        update["height_unit"] = body.height_unit
    if body.weight is not None:
        update["weight_kg"] = Decimal(str(body.weight))
    if body.weight_unit is not None:
        update["weight_unit"] = body.weight_unit
    if body.goal is not None:
        update["goal"] = body.goal
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

    # target_weight: конвертируем в кг если пользователь в фунтах
    if body.target_weight is not None:
        tw = body.target_weight
        w_unit = body.weight_unit or draft.weight_unit
        if w_unit == "lbs":
            tw = tw / 2.205
        update["target_weight"] = Decimal(str(round(tw, 1)))

    await OnboardingDraft.filter(user_id=user.telegram_id).update(**update)
    return {"ok": True}


@router.post("/complete")
async def complete_onboarding(auth_data: WebAppInitData = Depends(auth)):
    """
    Завершает онбординг:
    1. Читает черновик, проверяет наличие обязательных полей
    2. Создаёт UserProfile (или обновляет если почему-то уже есть)
    3. Пересчитывает DailyGoal
    4. Удаляет черновик
    """
    user = await get_or_create_user(
        auth_data.user.id,
        auth_data.user.first_name or "Unknown",
        auth_data.user.username,
    )

    draft = await OnboardingDraft.get_or_none(user_id=user.telegram_id)
    if not draft:
        raise HTTPException(status_code=400, detail="No onboarding draft found")

    # Валидация обязательных полей
    required = {
        "gender": draft.gender,
        "age": draft.age,
        "height_cm": draft.height_cm,
        "weight_kg": draft.weight_kg,
        "goal": draft.goal,
        "activity_level": draft.activity_level,
        "water_track": draft.water_track,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Onboarding incomplete. Missing: {', '.join(missing)}",
        )

    # Конвертируем activity_level float → строку для goal_calculator
    activity_str = ACTIVITY_MAP.get(draft.activity_level, "moderate")

    # Рассчитываем water_goal:
    # - 'auto'   → из DailyGoal (вес * 33), ставим None — пересчитается в _recalculate_goals
    # - 'manual' → берём из черновика
    # - 'none'   → не отслеживаем, ставим None
    water_goal_ml = draft.water_goal_ml if draft.water_track == "manual" else None

    profile_data = {
        "gender": draft.gender,
        "age": draft.age,
        "height_cm": draft.height_cm,
        "weight_kg": float(draft.weight_kg),
        "goal_type": draft.goal,
        "activity_level": activity_str,
        "dietary_restrictions": draft.dietary_restrictions,
        "medical_conditions": draft.medical_conditions,
    }

    existing = await UserProfile.get_or_none(user_id=user.telegram_id)
    if existing:
        await UserProfile.filter(user_id=user.telegram_id).update(
            **profile_data,
            height_unit=draft.height_unit,
            weight_unit=draft.weight_unit,
            target_weight_kg=draft.target_weight,
            water_track=draft.water_track,
            water_goal_ml=water_goal_ml,
            allergy_note=draft.allergy_note,
        )
        profile = await UserProfile.get(user_id=user.telegram_id)
    else:
        profile = await UserProfile.create(
            user_id=user.telegram_id,
            **profile_data,
            height_unit=draft.height_unit,
            weight_unit=draft.weight_unit,
            target_weight_kg=draft.target_weight,
            water_track=draft.water_track,
            water_goal_ml=water_goal_ml,
            allergy_note=draft.allergy_note,
        )
        # Первая запись в историю веса
        await WeightHistory.create(
            user_id=user.telegram_id, weight_kg=profile.weight_kg
        )

    # Пересчёт DailyGoal через формулу + Gemini
    await _recalculate_goals(user.telegram_id, profile)

    # Черновик больше не нужен
    await draft.delete()

    return {"ok": True}
