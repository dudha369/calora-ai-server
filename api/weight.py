"""
GET    /api/weight        — история взвешиваний (для графика и списка на WeightPage)
POST   /api/weight        — залогировать новое взвешивание (+ опциональная заметка).
                             Обновляет текущий вес в профиле и пересчитывает DailyGoal —
                             тот же эффект, что раньше давал PUT /api/profile с новым
                             весом, но явным отдельным эндпоинтом, без необходимости
                             пересылать весь остальной профиль.
DELETE /api/weight/{id}   — удалить запись взвешивания.

Поддерживает пагинацию: ?limit=90&offset=0
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .utils import get_current_user, parse_date
from .profile import _recalculate_goals
from db import User, UserProfile, WeightHistory, WeightHistorySchema

router = APIRouter(prefix="/api/weight", tags=["weight"])


class WeightIn(BaseModel):
    weight_kg: float = Field(gt=0, lt=400)
    note: Optional[str] = Field(default=None, max_length=200)
    log_date: Optional[str] = None  # "YYYY-MM-DD", по умолчанию — сегодня


@router.get("")
async def get_weight_history(
    limit: int = Query(90, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    """Записи взвешиваний для графика прогресса. По умолчанию последние 90."""
    records = (
        await WeightHistory.filter(user_id=user.telegram_id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        (await WeightHistorySchema.from_tortoise_orm(r)).model_dump() for r in records
    ]


@router.post("")
async def log_weight(body: WeightIn, user: User = Depends(get_current_user)):
    """
    Логирует новое взвешивание. Обновляет UserProfile.weight_kg и пересчитывает
    DailyGoal — та же семантика, что раньше давал PUT /api/profile при смене
    веса, но отдельным явным эндпоинтом, без необходимости пересылать весь профиль.
    """
    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    log_date = parse_date(body.log_date) if body.log_date else date.today()
    new_weight = Decimal(str(body.weight_kg))

    record = await WeightHistory.create(
        user_id=user.telegram_id,
        weight_kg=new_weight,
        log_date=log_date,
        note=body.note,
    )

    await UserProfile.filter(user_id=user.telegram_id).update(weight_kg=new_weight)
    await profile.refresh_from_db()
    await _recalculate_goals(user.telegram_id, profile)

    return (await WeightHistorySchema.from_tortoise_orm(record)).model_dump()


@router.delete("/{log_id}")
async def delete_weight(log_id: int, user: User = Depends(get_current_user)):
    deleted = await WeightHistory.filter(id=log_id, user_id=user.telegram_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"deleted": True}
