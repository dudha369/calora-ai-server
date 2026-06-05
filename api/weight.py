"""
GET  /api/weight        — история взвешиваний (для графика)
Обновление веса — через PUT /api/profile (вес часть профиля).
"""

from fastapi import APIRouter, Depends
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
from db import WeightHistory, WeightHistorySchema

router = APIRouter(prefix="/api/weight", tags=["weight"])


@router.get("")
async def get_weight_history(auth_data: WebAppInitData = Depends(auth)):
    """Последние 90 записей взвешиваний для графика прогресса."""
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    records = await WeightHistory.filter(user_id=user.telegram_id).limit(90).all()
    return [
        (await WeightHistorySchema.from_tortoise_orm(r)).model_dump() for r in records
    ]
