"""
GET /api/stats/daily?date=YYYY-MM-DD
    — суммарное потребление за день + цели из DailyGoal.
      Возвращает нули, если записей нет (не 404).

GET /api/stats/active-dates?from=YYYY-MM-DD&to=YYYY-MM-DD
    — список дат в диапазоне, где есть хотя бы одна запись
      в FoodLog или WaterLog. Используется для окраски карусели дат.
"""

from fastapi import APIRouter, Depends, Query
from tortoise.exceptions import DoesNotExist

from .utils import get_current_user, parse_date
from db import User, FoodLog, WaterLog, DailyGoal

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/daily")
async def get_daily_stats(
    date: str,
    user: User = Depends(get_current_user),
):
    d = parse_date(date)

    # — Суммируем FoodLog за день —
    food_logs = await FoodLog.filter(user_id=user.telegram_id, log_date=d).all()
    calories = sum(log.total_calories for log in food_logs)
    protein_g = sum(float(log.total_protein_g) for log in food_logs)
    fat_g = sum(float(log.total_fat_g) for log in food_logs)
    carbs_g = sum(float(log.total_carbs_g) for log in food_logs)

    # — Суммируем WaterLog за день —
    water_logs = await WaterLog.filter(user_id=user.telegram_id, log_date=d).all()
    water_ml = sum(log.amount_ml for log in water_logs)

    has_data = bool(food_logs or water_logs)

    # — Цели из DailyGoal (нули если онбординг не пройден) —
    calories_goal = 0
    protein_goal_g = 0.0
    fat_goal_g = 0.0
    carbs_goal_g = 0.0
    water_goal_ml = 0

    try:
        goal = await DailyGoal.get(user_id=user.telegram_id)
        calories_goal = goal.calories
        protein_goal_g = float(goal.protein_g)
        fat_goal_g = float(goal.fat_g)
        carbs_goal_g = float(goal.carbs_g)
        water_goal_ml = goal.water_ml
    except DoesNotExist:
        pass

    return {
        "calories": calories,
        "protein_g": round(protein_g, 1),
        "fat_g": round(fat_g, 1),
        "carbs_g": round(carbs_g, 1),
        "water_ml": water_ml,
        "calories_goal": calories_goal,
        "protein_goal_g": round(protein_goal_g, 1),
        "fat_goal_g": round(fat_goal_g, 1),
        "carbs_goal_g": round(carbs_goal_g, 1),
        "water_goal_ml": water_goal_ml,
        "has_data": has_data,
    }


@router.get("/active-dates")
async def get_active_dates(
    from_: str = Query(..., alias="from"),  # "from" — keyword в Python
    to: str = Query(...),
    user: User = Depends(get_current_user),
):
    """
    Возвращает по каждой активной дате отдельные флаги has_food/has_water
    (а не плоский список) — нужно для UI-маркеров в DateStrip/Calendar,
    которые красят точку по-разному в зависимости от того, что именно
    залогировано в этот день.
    """
    d_from = parse_date(from_)
    d_to = parse_date(to)

    food_dates = await FoodLog.filter(
        user_id=user.telegram_id,
        log_date__gte=d_from,
        log_date__lte=d_to,
    ).values_list("log_date", flat=True)

    water_dates = await WaterLog.filter(
        user_id=user.telegram_id,
        log_date__gte=d_from,
        log_date__lte=d_to,
    ).values_list("log_date", flat=True)

    food_set = {d.isoformat() for d in food_dates}
    water_set = {d.isoformat() for d in water_dates}
    all_dates = sorted(food_set | water_set)

    return {
        "dates": [
            {"date": d, "has_food": d in food_set, "has_water": d in water_set}
            for d in all_dates
        ]
    }
