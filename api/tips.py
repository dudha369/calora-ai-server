"""
GET /api/tips/today — совет за сегодня (создаёт если нет)
GET /api/tips       — последние N советов (пагинация: ?limit=7&offset=0)
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query

from .utils import get_current_user
from db import User, AiTip, AiTipSchema, FoodLog, DailyGoal
from ai.services.tip_generator import generate_daily_tip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tips", tags=["tips"])


@router.get("/today")
async def get_today_tip(user: User = Depends(get_current_user)):
    """
    Возвращает совет за сегодня.
    Если нет — генерирует на основе еды за сегодня (если есть хоть одна запись).
    """
    today = date.today()

    existing = await AiTip.get_or_none(user_id=user.telegram_id, based_on_date=today)
    if existing:
        return (await AiTipSchema.from_tortoise_orm(existing)).model_dump()

    # Собираем данные за сегодня
    logs = await FoodLog.filter(user_id=user.telegram_id, log_date=today).all()
    if not logs:
        return {
            "tip": None,
            "message": "Добавь первую запись еды — получишь персональный совет!",
        }

    goal = await DailyGoal.get_or_none(user_id=user.telegram_id)
    goals = {
        "calories": goal.calories if goal else 2000,
        "protein_g": float(goal.protein_g) if goal else 100,
        "fat_g": float(goal.fat_g) if goal else 65,
        "carbs_g": float(goal.carbs_g) if goal else 250,
        "water_ml": goal.water_ml if goal else 2000,
    }

    today_summary = {
        "total_calories": sum(l.total_calories for l in logs),
        "total_protein_g": sum(float(l.total_protein_g) for l in logs),
        "total_fat_g": sum(float(l.total_fat_g) for l in logs),
        "total_carbs_g": sum(float(l.total_carbs_g) for l in logs),
    }

    try:
        tip_data = await generate_daily_tip(goals, today_summary)
        tip = await AiTip.create(
            user_id=user.telegram_id,
            tip_text=tip_data["tip"],
            tip_type=tip_data.get("tip_type", "general"),
            icon=tip_data.get("icon", "💡"),
            based_on_date=today,
        )
        return (await AiTipSchema.from_tortoise_orm(tip)).model_dump()
    except Exception as e:
        logger.error(f"Tip generation failed for user {user.telegram_id}: {e}")
        return {
            "tip": None,
            "message": "Не удалось сгенерировать совет, попробуй позже",
        }


@router.get("")
async def get_recent_tips(
    limit: int = Query(7, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    """Последние советы с пагинацией."""
    tips = (
        await AiTip.filter(user_id=user.telegram_id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [(await AiTipSchema.from_tortoise_orm(t)).model_dump() for t in tips]
