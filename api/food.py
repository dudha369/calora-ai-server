"""
POST /api/food/analyze    — анализ фото через Gemini (не сохраняет)
POST /api/food/log        — сохранить запись еды
GET  /api/food/{date}     — все записи за дату (YYYY-MM-DD)
DELETE /api/food/{log_id} — удалить запись
"""

import asyncio
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
from db import FoodLog, FoodLogSchema, FoodItem, FoodItemSchema
from ai.services.food_analyzer import analyze_food_photo
from services.storage import upload_food_photo, get_photo_url

router = APIRouter(prefix="/api/food", tags=["food"])


class FoodItemIn(BaseModel):
    food_name: str
    portion_g: float
    calories: int
    protein_g: float
    fat_g: float
    carbs_g: float


class FoodLogIn(BaseModel):
    log_date: str
    items: list[FoodItemIn]
    photo_key: Optional[str] = None   # ключ объекта в B2, не URL


async def _recalc_totals(food_log: FoodLog) -> None:
    items = await FoodItem.filter(food_log_id=food_log.id).all()
    await FoodLog.filter(id=food_log.id).update(
        total_calories=sum(i.calories for i in items),
        total_protein_g=sum(float(i.protein_g) for i in items),
        total_fat_g=sum(float(i.fat_g) for i in items),
        total_carbs_g=sum(float(i.carbs_g) for i in items),
    )


@router.post("/analyze")
async def analyze_photo(
    file: UploadFile = File(...),
    auth_data: WebAppInitData = Depends(auth),
):
    """
    Принимает фото, параллельно:
    - отправляет в Gemini для анализа КБЖУ
    - загружает в Backblaze B2 (приватный бакет)

    Возвращает найденные блюда + photo_key (ключ объекта в B2).
    photo_key нужно передать в POST /log чтобы фото привязалось к записи.
    """
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    result, photo_key = await asyncio.gather(
        analyze_food_photo(image_bytes, mime_type),
        upload_food_photo(image_bytes, auth_data.user.id, mime_type),
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return {**result, "photo_key": photo_key}


@router.post("/log")
async def create_log(body: FoodLogIn, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    log_date = date.fromisoformat(body.log_date)

    food_log = await FoodLog.create(
        user_id=user.telegram_id,
        log_date=log_date,
        photo_url=body.photo_key,   # храним ключ B2 в колонке photo_url
    )

    for item in body.items:
        await FoodItem.create(
            food_log_id=food_log.id,
            food_name=item.food_name,
            portion_g=Decimal(str(item.portion_g)),
            calories=item.calories,
            protein_g=Decimal(str(item.protein_g)),
            fat_g=Decimal(str(item.fat_g)),
            carbs_g=Decimal(str(item.carbs_g)),
        )

    await _recalc_totals(food_log)
    await food_log.refresh_from_db()

    items_data = await FoodItemSchema.from_queryset(
        FoodItem.filter(food_log_id=food_log.id)
    )
    log_dict = (await FoodLogSchema.from_tortoise_orm(food_log)).model_dump()

    return {
        "log": {**log_dict, "photo_url": await get_photo_url(food_log.photo_url)},
        "items": [i.model_dump() for i in items_data],
    }


@router.get("/{log_date}")
async def get_logs_by_date(log_date: str, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    d = date.fromisoformat(log_date)
    logs = await FoodLog.filter(
        user_id=user.telegram_id, log_date=d
    ).prefetch_related("items")

    # Генерируем presigned URL для всех фото параллельно
    photo_urls = await asyncio.gather(
        *[get_photo_url(log.photo_url) for log in logs]
    )

    result = []
    for log, photo_url in zip(logs, photo_urls):
        log_dict = (await FoodLogSchema.from_tortoise_orm(log)).model_dump()
        items = await FoodItemSchema.from_queryset(
            FoodItem.filter(food_log_id=log.id)
        )
        result.append({
            **log_dict,
            "photo_url": photo_url,   # presigned URL или None
            "items": [i.model_dump() for i in items],
        })

    return {
        "date": log_date,
        "logs": result,
        "daily_total": {
            "calories":   sum(l["total_calories"]       for l in result),
            "protein_g":  sum(float(l["total_protein_g"]) for l in result),
            "fat_g":      sum(float(l["total_fat_g"])     for l in result),
            "carbs_g":    sum(float(l["total_carbs_g"])   for l in result),
        },
    }


@router.delete("/{log_id}")
async def delete_log(log_id: int, auth_data: WebAppInitData = Depends(auth)):
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    deleted = await FoodLog.filter(id=log_id, user_id=user.telegram_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"deleted": True}
