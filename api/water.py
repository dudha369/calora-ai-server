"""
POST /api/water      — добавить запись воды
GET  /api/water/{date} — вода за день
DELETE /api/water/{log_id}
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .utils import get_current_user
from db import User, WaterLog, WaterLogSchema

router = APIRouter(prefix="/api/water", tags=["water"])


class WaterIn(BaseModel):
    log_date: str  # "2026-05-26"
    amount_ml: int  # 250 | 400 | 500


@router.post("")
async def add_water(body: WaterIn, user: User = Depends(get_current_user)):
    log = await WaterLog.create(
        user_id=user.telegram_id,
        log_date=date.fromisoformat(body.log_date),
        amount_ml=body.amount_ml,
    )
    return (await WaterLogSchema.from_tortoise_orm(log)).model_dump()


@router.get("/{log_date}")
async def get_water_by_date(log_date: str, user: User = Depends(get_current_user)):
    d = date.fromisoformat(log_date)
    logs = await WaterLog.filter(user_id=user.telegram_id, log_date=d).all()
    total_ml = sum(l.amount_ml for l in logs)
    return {
        "date": log_date,
        "logs": [
            (await WaterLogSchema.from_tortoise_orm(l)).model_dump() for l in logs
        ],
        "total_ml": total_ml,
    }


@router.delete("/{log_id}")
async def delete_water(log_id: int, user: User = Depends(get_current_user)):
    deleted = await WaterLog.filter(id=log_id, user_id=user.telegram_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"deleted": True}
