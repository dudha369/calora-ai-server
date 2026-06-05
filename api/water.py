"""
POST /api/water      — добавить запись воды
GET  /api/water/{date} — вода за день
DELETE /api/water/{log_id}
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
from db import WaterLog, WaterLogSchema

router = APIRouter(prefix="/api/water", tags=["water"])


class WaterIn(BaseModel):
    log_date: str  # "2026-05-26"
    amount_ml: int  # 250 | 400 | 500


@router.post("")
async def add_water(body: WaterIn, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    log = await WaterLog.create(
        user_id=user.telegram_id,
        log_date=date.fromisoformat(body.log_date),
        amount_ml=body.amount_ml,
    )
    return (await WaterLogSchema.from_tortoise_orm(log)).model_dump()


@router.get("/{log_date}")
async def get_water_by_date(log_date: str, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
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
async def delete_water(log_id: int, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    deleted = await WaterLog.filter(id=log_id, user_id=user.telegram_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"deleted": True}
