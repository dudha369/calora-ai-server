"""
POST   /api/water            — добавить запись воды
                                (можно сразу приложить заметку и/или привязать к еде)
GET    /api/water/{date}     — вода за день + сумма + краткая карточка привязанного блюда
PATCH  /api/water/{log_id}   — изменить заметку и/или привязку к еде
                                (не переданное поле = не трогаем, PATCH-семантика)
DELETE /api/water/{log_id}
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .utils import get_current_user, parse_date
from db import User, WaterLog, WaterLogSchema, FoodLog, FoodItem

router = APIRouter(prefix="/api/water", tags=["water"])


class WaterIn(BaseModel):
    log_date: str  # "2026-05-26"
    amount_ml: int  # 250 | 400 | 500
    notes: Optional[str] = None
    food_log_id: Optional[int] = None  # привязка сразу при создании


class WaterUpdate(BaseModel):
    """
    PATCH-тело: любое поле, ОТСУТСТВУЮЩЕЕ в запросе, не трогается
    (см. model_dump(exclude_unset=True) ниже). Явный null у notes/food_log_id
    применяется — так notes=null очищает заметку, а food_log_id=null
    отвязывает запись от еды.
    """

    amount_ml: Optional[int] = None
    notes: Optional[str] = None
    food_log_id: Optional[int] = None


async def _validate_food_log(food_log_id: int, user_id: int) -> None:
    exists = await FoodLog.filter(id=food_log_id, user_id=user_id).exists()
    if not exists:
        raise HTTPException(status_code=404, detail="Food log not found")


async def _food_log_summary(food_log_id: Optional[int], user_id: int) -> Optional[dict]:
    """
    Краткая карточка привязанного приёма пищи для WaterLogModal.
    Тот же принцип отображаемого имени, что и в FoodLogCard на фронте:
    meal_name, а если его нет — имя первого блюда в логе.
    """
    if not food_log_id:
        return None

    food_log = await FoodLog.get_or_none(id=food_log_id, user_id=user_id)
    if not food_log:
        # Блюдо было удалено, а WaterLog остался отвязан (food_log ON DELETE
        # SET NULL сработает своим чередом) — до этого момента просто не
        # показываем карточку, чтобы не падать.
        return None

    first_item = await FoodItem.filter(food_log_id=food_log.id).first()

    return {
        "id": food_log.id,
        "log_date": food_log.log_date.isoformat(),
        "meal_name": food_log.meal_name,
        "first_item_name": first_item.food_name if first_item else None,
        "logged_at": food_log.logged_at.isoformat(),
    }


async def _serialize(log: WaterLog) -> dict:
    data = (await WaterLogSchema.from_tortoise_orm(log)).model_dump()
    data["linked_food_log"] = await _food_log_summary(log.food_log_id, log.user_id)
    return data


@router.post("")
async def add_water(body: WaterIn, user: User = Depends(get_current_user)):
    if body.food_log_id is not None:
        await _validate_food_log(body.food_log_id, user.telegram_id)

    log = await WaterLog.create(
        user_id=user.telegram_id,
        log_date=parse_date(body.log_date),
        amount_ml=body.amount_ml,
        notes=body.notes,
        food_log_id=body.food_log_id,
    )
    return await _serialize(log)


@router.get("/{log_date}")
async def get_water_by_date(log_date: str, user: User = Depends(get_current_user)):
    d = parse_date(log_date)
    logs = await WaterLog.filter(user_id=user.telegram_id, log_date=d).all()
    total_ml = sum(l.amount_ml for l in logs)
    return {
        "date": log_date,
        "logs": [await _serialize(l) for l in logs],
        "total_ml": total_ml,
    }


@router.patch("/{log_id}")
async def update_water(
    log_id: int, body: WaterUpdate, user: User = Depends(get_current_user)
):
    log = await WaterLog.get_or_none(id=log_id, user_id=user.telegram_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    update = body.model_dump(exclude_unset=True)

    if update.get("food_log_id") is not None:
        await _validate_food_log(update["food_log_id"], user.telegram_id)

    if update:
        await WaterLog.filter(id=log_id).update(**update)
        await log.refresh_from_db()

    return await _serialize(log)


@router.delete("/{log_id}")
async def delete_water(log_id: int, user: User = Depends(get_current_user)):
    deleted = await WaterLog.filter(id=log_id, user_id=user.telegram_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"deleted": True}
