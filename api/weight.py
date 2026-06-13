"""
GET  /api/weight        — история взвешиваний (для графика)
Обновление веса — через PUT /api/profile (вес часть профиля).

Поддерживает пагинацию: ?limit=90&offset=0
"""

from fastapi import APIRouter, Depends, Query

from .utils import get_current_user
from db import User, WeightHistory, WeightHistorySchema

router = APIRouter(prefix="/api/weight", tags=["weight"])


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
