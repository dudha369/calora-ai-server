"""
POST /api/food/analyze    — анализ фото через Gemini (не сохраняет)
POST /api/food/log        — сохранить запись еды
POST /api/food/log-barcode — сохранить запись по штрихкоду
GET  /api/food/{date}     — все записи за дату (YYYY-MM-DD)
DELETE /api/food/{log_id} — удалить запись (+ фото из B2)
DELETE /api/food/photo/{photo_key:path} — удалить неиспользованное фото

/analyze принимает опциональное поле формы `notes` — уточнение пользователя,
введённое после съёмки фото (см. ai/services/food_analyzer.py).

/log принимает опциональное поле `water_ml` — суммарную гидратацию,
которую ИИ нашёл среди распознанных блюд/напитков. Если оно больше 0,
после сохранения FoodLog автоматически создаётся запись в WaterLog —
так вода логируется без отдельного действия пользователя.
"""

import asyncio
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from .utils import auth, get_current_user, check_rate_limit, parse_date
from db import (
    User,
    FoodLog,
    FoodLogSchema,
    FoodItem,
    FoodItemSchema,
    UserProfile,
    DailyGoal,
    WaterLog,
)
from ai.gemini import GeminiUnavailableError
from ai.services.food_analyzer import analyze_food_photo
from services.storage import upload_food_photo, get_photo_url, delete_food_photo
from services.streaks import sync_today_credit_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/food", tags=["food"])

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_ANALYZE_PER_MINUTE = 5
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
MAX_NOTES_LENGTH = 300

# Паттерн валидного photo_key: food/{user_id}/{uuid}.{ext}
_PHOTO_KEY_RE = re.compile(r"^food/\d+/[a-f0-9]+\.\w+$")


# ─── Pydantic models ─────────────────────────────────────────────────────────


class FoodItemIn(BaseModel):
    food_name: str
    portion_g: float
    calories: int
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float = 0.0
    sugar_g: float = 0.0


class FoodLogIn(BaseModel):
    log_date: str
    items: list[FoodItemIn]
    photo_key: Optional[str] = None  # ключ объекта в B2, не URL
    # Суммарная гидратация, найденная ИИ среди блюд/напитков на фото.
    # Если > 0 — после сохранения FoodLog автоматически создаётся WaterLog.
    water_ml: Optional[int] = None


class BarcodeLogIn(BaseModel):
    log_date: str
    items: list[FoodItemIn]  # одна позиция, посчитанная на фронте из OFF-данных


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _maybe_sync_streak(user: User, log_date: date) -> None:
    """
    Побочный эффект любого изменения FoodLog за сегодня (создание или удаление).
    sync_today_credit_state сама разберётся, нужно ли начислить, снять или
    оставить всё как есть — вызывать одну функцию безопасно в обоих случаях.
    """
    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    if not profile:
        return
    goal = await DailyGoal.get_or_none(user_id=user.telegram_id)
    if not goal:
        return
    await sync_today_credit_state(user, goal, profile.timezone, log_date)


async def _maybe_log_water(user: User, log_date: date, water_ml: Optional[int]) -> None:
    """
    Побочный эффект записи еды: если ИИ нашёл воду/напитки на фото, создаёт
    запись в WaterLog для той же даты. Best-effort, как и _maybe_credit_streak —
    ошибка здесь не должна ронять сохранение самой еды.
    """
    if not water_ml or water_ml <= 0:
        return
    try:
        await WaterLog.create(
            user_id=user.telegram_id, log_date=log_date, amount_ml=water_ml
        )
    except Exception:
        logger.exception("auto water log failed for user %s", user.telegram_id)


async def _recalc_totals(food_log: FoodLog) -> None:
    items = await FoodItem.filter(food_log_id=food_log.id).all()
    await FoodLog.filter(id=food_log.id).update(
        total_calories=sum(i.calories for i in items),
        total_protein_g=sum(float(i.protein_g) for i in items),
        total_fat_g=sum(float(i.fat_g) for i in items),
        total_carbs_g=sum(float(i.carbs_g) for i in items),
        total_fiber_g=sum(float(i.fiber_g) for i in items),
        total_sugar_g=sum(float(i.sugar_g) for i in items),
    )


async def _create_log_with_items(
    user: User,
    body_log_date: str,
    body_items: list[FoodItemIn],
    photo_key: Optional[str] = None,
    water_ml: Optional[int] = None,
) -> dict:
    """Общая логика создания FoodLog + FoodItems для /log и /log-barcode."""
    log_date = parse_date(body_log_date)

    food_log = await FoodLog.create(
        user_id=user.telegram_id,
        log_date=log_date,
        photo_url=photo_key,
    )

    for item in body_items:
        await FoodItem.create(
            food_log_id=food_log.id,
            food_name=item.food_name,
            portion_g=Decimal(str(item.portion_g)),
            calories=item.calories,
            protein_g=Decimal(str(item.protein_g)),
            fat_g=Decimal(str(item.fat_g)),
            carbs_g=Decimal(str(item.carbs_g)),
            fiber_g=Decimal(str(item.fiber_g)),
            sugar_g=Decimal(str(item.sugar_g)),
        )

    await _recalc_totals(food_log)
    await food_log.refresh_from_db()

    # Побочные эффекты, не основная функция эндпоинта — баг здесь не должен
    # ронять сохранение еды.
    try:
        await _maybe_sync_streak(user, log_date)
    except Exception:
        logger.exception("streak credit failed for user %s", user.telegram_id)

    await _maybe_log_water(user, log_date, water_ml)

    items_data = await FoodItemSchema.from_queryset(
        FoodItem.filter(food_log_id=food_log.id)
    )
    log_dict = (await FoodLogSchema.from_tortoise_orm(food_log)).model_dump()

    return {
        "log": {**log_dict, "photo_url": await get_photo_url(photo_key)},
        "items": [i.model_dump() for i in items_data],
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/log-barcode")
async def create_log_from_barcode(
    body: BarcodeLogIn, user: User = Depends(get_current_user)
):
    """
    Логирование еды по штрихкоду (OpenFoodFacts).
    photo_url всегда NULL — фото штрихкода не несёт пищевой информации.
    """
    return await _create_log_with_items(user, body.log_date, body.items, photo_key=None)


@router.post("/analyze")
async def analyze_photo(
    request: Request,
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None, max_length=MAX_NOTES_LENGTH),
    user: User = Depends(get_current_user),
):
    # ── Rate limiting ──
    check_rate_limit(
        user.telegram_id, bucket="analyze", max_per_minute=MAX_ANALYZE_PER_MINUTE
    )

    # ── MIME validation ──
    mime_type = file.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime_type}. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # ── File size limit ──
    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB",
        )

    # Загружаем фото параллельно с анализом — экономим ~300-500ms
    try:
        result, photo_key = await asyncio.gather(
            analyze_food_photo(image_bytes, mime_type, notes=notes),
            upload_food_photo(image_bytes, user.telegram_id, mime_type),
        )
    except GeminiUnavailableError as exc:
        logger.warning("Gemini unavailable for user %s: %s", user.telegram_id, exc)
        raise HTTPException(
            status_code=503,
            detail="AI model is temporarily overloaded. Please try again in a moment.",
        )
    except Exception as exc:
        logger.error("Food analysis failed for user %s: %s", user.telegram_id, exc)
        raise HTTPException(status_code=500, detail="Food analysis failed.")

    if "error" in result:
        await delete_food_photo(photo_key)
        raise HTTPException(status_code=422, detail=result["error"])

    return {**result, "photo_key": photo_key}


@router.post("/log")
async def create_log(body: FoodLogIn, user: User = Depends(get_current_user)):
    return await _create_log_with_items(
        user,
        body.log_date,
        body.items,
        photo_key=body.photo_key,
        water_ml=body.water_ml,
    )


@router.get("/{log_date}")
async def get_logs_by_date(log_date: str, user: User = Depends(get_current_user)):
    d = parse_date(log_date)
    logs = await FoodLog.filter(user_id=user.telegram_id, log_date=d).prefetch_related(
        "items"
    )

    photo_urls = await asyncio.gather(*[get_photo_url(log.photo_url) for log in logs])

    result = []
    for log, photo_url in zip(logs, photo_urls):
        log_dict = (await FoodLogSchema.from_tortoise_orm(log)).model_dump()
        items = await FoodItemSchema.from_queryset(FoodItem.filter(food_log_id=log.id))
        result.append(
            {
                **log_dict,
                "photo_url": photo_url,
                "items": [i.model_dump() for i in items],
            }
        )

    return {
        "date": log_date,
        "logs": result,
        "daily_total": {
            "calories": sum(l["total_calories"] for l in result),
            "protein_g": sum(float(l["total_protein_g"]) for l in result),
            "fat_g": sum(float(l["total_fat_g"]) for l in result),
            "carbs_g": sum(float(l["total_carbs_g"]) for l in result),
            "fiber_g": sum(float(l["total_fiber_g"]) for l in result),
            "sugar_g": sum(float(l["total_sugar_g"]) for l in result),
        },
    }


@router.delete("/photo/{photo_key:path}")
async def delete_orphan_photo(photo_key: str, user: User = Depends(get_current_user)):
    """
    Удаляет фото из B2, которое не было привязано к FoodLog.

    Вызывается клиентом когда пользователь закрывает модалку подтверждения
    после /analyze не нажав «Добавить» — фото уже в B2, но photo_key
    не попал в БД.

    Безопасность:
    - Валидация формата ключа через regex
    - Проверка принадлежности фото текущему пользователю
    - Проверка что фото не используется ни одним FoodLog
    """
    if not _PHOTO_KEY_RE.match(photo_key):
        raise HTTPException(status_code=400, detail="Invalid photo key format")

    expected_prefix = f"food/{user.telegram_id}/"
    if not photo_key.startswith(expected_prefix):
        raise HTTPException(
            status_code=403, detail="Cannot delete another user's photo"
        )

    existing = await FoodLog.filter(
        user_id=user.telegram_id, photo_url=photo_key
    ).exists()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Photo is in use by a food log. Delete the log instead.",
        )

    await delete_food_photo(photo_key)
    return {"deleted": True}


@router.delete("/{log_id}")
async def delete_log(log_id: int, user: User = Depends(get_current_user)):
    food_log = await FoodLog.get_or_none(id=log_id, user_id=user.telegram_id)
    if not food_log:
        raise HTTPException(status_code=404, detail="Log not found")

    if food_log.photo_url:
        await delete_food_photo(food_log.photo_url)

    deleted_log_date = food_log.log_date
    await FoodLog.filter(id=log_id).delete()

    try:
        await _maybe_sync_streak(user, deleted_log_date)
    except Exception:
        logger.exception("streak uncredit failed for user %s", user.telegram_id)

    return {"deleted": True}
