"""
POST /api/food/analyze    — анализ фото через Gemini (не сохраняет)
POST /api/food/log        — сохранить запись еды
POST /api/food/log-barcode — сохранить запись по штрихкоду
PUT  /api/food/{log_id}   — редактировать запись (заменить items, пересчитать)
GET  /api/food/{date}     — все записи за дату (YYYY-MM-DD)
DELETE /api/food/{log_id} — удалить запись (+ фото из B2)
DELETE /api/food/photo/{photo_key:path} — удалить неиспользованное фото

/analyze принимает опциональное поле формы `notes` — уточнение пользователя,
введённое после съёмки фото (см. ai/services/food_analyzer.py).

Вода: по одной WaterLog-записи на КАЖДОЕ блюдо/напиток с water_ml > 0
(см. _create_auto_water_logs), а не одна агрегированная запись на весь
приём пищи — так "Омлет + Горячий шоколад" даёт запись воды с именем
"Горячий шоколад", а не название всего приёма пищи. При PUT /{log_id}
такие записи не пересоздаются с нуля, а сопоставляются со старыми по
имени блюда и обновляются на месте (logged_at и заметки не теряются).
"""

import asyncio
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
    Query,
)
from pydantic import BaseModel, Field

from .utils import get_current_user, check_rate_limit, parse_date, release_rate_limit
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
from ai.gemini import GeminiUnavailableError, GeminiQuotaExceededError
from ai.services.food_analyzer import (
    analyze_food_photo,
    analyze_food_text,
    transcribe_voice,
)
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
    water_ml: int = 0  # per-dish hydration, источник истины для WaterLog


class FoodLogIn(BaseModel):
    log_date: str
    items: list[FoodItemIn]
    photo_key: Optional[str] = None  # ключ объекта в B2, не URL
    meal_name: Optional[str] = None  # обобщающее название приёма пищи (из AI)
    # Устаревшее поле: раньше задавало суммарную гидратацию на весь лог.
    # Больше не используется бэкендом (вода считается по item.water_ml),
    # оставлено опциональным, чтобы не ломать фронт, который иногда его шлёт.
    water_ml: Optional[int] = None
    # Копирование фото из существующего FoodLog (по id).
    # Если указан и photo_key не задан — берём photo_url (ключ B2) из
    # указанного лога (только если он принадлежит тому же пользователю).
    copy_photo_from_log_id: Optional[int] = None


class FoodLogUpdate(BaseModel):
    """Тело PUT /api/food/{log_id} — полная замена items.

    meal_name опционален и применяется только когда после правки остаётся
    больше одного item — см. update_log(): если остаётся ровно один item,
    meal_name принудительно становится названием этого item'а (та же логика,
    что и в промпте ИИ и в CopyMealSheet на фронте), независимо от того, что
    было передано в этом поле.

    remove_photo — открепить фото от записи. Как и delete_log, физически
    удаляет объект из B2 только если ни одна ДРУГАЯ запись пользователя
    на него больше не ссылается (общее фото могло появиться через
    copy_photo_from_log_id при копировании приёма пищи).
    """

    items: list[FoodItemIn]
    meal_name: Optional[str] = None
    remove_photo: bool = False


class BarcodeLogIn(BaseModel):
    log_date: str
    items: list[FoodItemIn]  # одна позиция, посчитанная на фронте из OFF-данных
    photo_key: Optional[str] = None  # обычно внешний URL картинки с OpenFoodFacts


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

    await sync_today_credit_state(
        user, goal, profile.timezone, log_date, profile.goal_type
    )


async def _recalc_totals(food_log: FoodLog) -> None:
    items = await FoodItem.filter(food_log_id=food_log.id).all()
    await FoodLog.filter(id=food_log.id).update(
        total_calories=sum(i.calories for i in items),
        total_protein_g=sum(float(i.protein_g) for i in items),
        total_fat_g=sum(float(i.fat_g) for i in items),
        total_carbs_g=sum(float(i.carbs_g) for i in items),
        total_fiber_g=sum(float(i.fiber_g) for i in items),
        total_sugar_g=sum(float(i.sugar_g) for i in items),
        total_water_ml=sum(i.water_ml for i in items),
    )


async def _create_auto_water_logs(
    user: User,
    log_date: date,
    food_log_id: int,
    items: list[FoodItem],
) -> None:
    """
    Один WaterLog на каждое блюдо/напиток с water_ml > 0 — а не один общий
    на весь приём пищи. Так "Омлет + Горячий шоколад" даёт запись воды
    с именем "Горячий шоколад" (см. WaterLog.food_item), а не всего
    приёма пищи целиком.
    """
    for item in items:
        if item.water_ml <= 0:
            continue
        try:
            await WaterLog.create(
                user_id=user.telegram_id,
                log_date=log_date,
                amount_ml=item.water_ml,
                food_log_id=food_log_id,
                food_item_id=item.id,
            )
        except Exception:
            logger.exception("auto water log failed for user %s", user.telegram_id)


async def _create_log_with_items(
    user: User,
    body_log_date: str,
    body_items: list[FoodItemIn],
    photo_key: Optional[str] = None,
    meal_name: Optional[str] = None,
) -> dict:
    """
    Общая логика создания FoodLog + FoodItems для /log и /log-barcode.

    Вода целиком определяется item.water_ml — по одной WaterLog-записи
    на каждое блюдо/напиток с водой (см. _create_auto_water_logs).
    """
    log_date = parse_date(body_log_date)

    food_log = await FoodLog.create(
        user_id=user.telegram_id,
        log_date=log_date,
        photo_url=photo_key,
        meal_name=meal_name,
    )

    created_items: list[FoodItem] = []
    for item in body_items:
        created_items.append(
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
                water_ml=item.water_ml,
            )
        )

    await _recalc_totals(food_log)
    await food_log.refresh_from_db()

    try:
        await _maybe_sync_streak(user, log_date)
    except Exception:
        logger.exception("streak credit failed for user %s", user.telegram_id)

    await _create_auto_water_logs(user, log_date, food_log.id, created_items)

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
    """Логирование еды по штрихкоду (OpenFoodFacts)."""
    return await _create_log_with_items(
        user, body.log_date, body.items, photo_key=body.photo_key
    )


@router.post("/analyze")
async def analyze_photo(
    request: Request,
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None, max_length=MAX_NOTES_LENGTH),
    language: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    check_rate_limit(
        user.telegram_id, bucket="analyze", max_per_minute=MAX_ANALYZE_PER_MINUTE
    )

    mime_type = file.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime_type}. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB",
        )

    try:
        result, photo_key = await asyncio.gather(
            analyze_food_photo(
                image_bytes,
                mime_type,
                notes=notes,
                language=language or user.language_code,
                user_id=user.telegram_id,
            ),
            upload_food_photo(image_bytes, user.telegram_id, mime_type),
        )
    except GeminiQuotaExceededError:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.warning("Gemini quota exceeded for user %s", user.telegram_id)
        raise HTTPException(status_code=429, detail="ai_quota_exceeded")
    except GeminiUnavailableError as exc:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.warning("Gemini unavailable for user %s: %s", user.telegram_id, exc)
        raise HTTPException(
            status_code=503,
            detail="AI model is temporarily overloaded. Please try again in a moment.",
        )
    except Exception as exc:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.error("Food analysis failed for user %s: %s", user.telegram_id, exc)
        raise HTTPException(status_code=500, detail="Food analysis failed.")

    if "error" in result:
        await delete_food_photo(photo_key)
        raise HTTPException(status_code=422, detail=result["error"])

    return {**result, "photo_key": photo_key}


MAX_TEXT_DESCRIPTION_LENGTH = 500


class FoodTextIn(BaseModel):
    description: str = Field(min_length=1, max_length=MAX_TEXT_DESCRIPTION_LENGTH)
    language: Optional[str] = None


@router.post("/analyze-text")
async def analyze_text(body: FoodTextIn, user: User = Depends(get_current_user)):
    check_rate_limit(
        user.telegram_id, bucket="analyze", max_per_minute=MAX_ANALYZE_PER_MINUTE
    )
    try:
        result = await analyze_food_text(
            body.description,
            language=body.language or user.language_code,
            user_id=user.telegram_id,
        )
    except GeminiQuotaExceededError:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.warning("Gemini quota exceeded for user %s", user.telegram_id)
        raise HTTPException(status_code=429, detail="ai_quota_exceeded")
    except GeminiUnavailableError as exc:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.warning("Gemini unavailable for user %s: %s", user.telegram_id, exc)
        raise HTTPException(
            status_code=503,
            detail="AI model is temporarily overloaded. Please try again in a moment.",
        )
    except Exception as exc:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.error("Food analysis failed for user %s: %s", user.telegram_id, exc)
        raise HTTPException(status_code=500, detail="Food analysis failed.")

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return {**result, "photo_key": None}


ALLOWED_AUDIO_MIME_TYPES = {"audio/wav", "audio/wave", "audio/x-wav"}
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # голосовые заметки короткие, лимит с запасом


@router.post("/transcribe-voice")
async def transcribe_voice_endpoint(
    file: UploadFile = File(...), user: User = Depends(get_current_user)
):
    """Голосовая запись → текст. Дальше фронт зовёт /analyze-text с этим текстом."""
    check_rate_limit(
        user.telegram_id, bucket="analyze", max_per_minute=MAX_ANALYZE_PER_MINUTE
    )

    mime_type = file.content_type or "audio/wav"
    if mime_type not in ALLOWED_AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type: {mime_type}. Expected WAV.",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {MAX_AUDIO_SIZE_BYTES // (1024 * 1024)} MB",
        )

    try:
        transcript = await transcribe_voice(audio_bytes, mime_type="audio/wav")
    except GeminiQuotaExceededError:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.warning("Gemini quota exceeded for user %s", user.telegram_id)
        raise HTTPException(status_code=429, detail="ai_quota_exceeded")
    except GeminiUnavailableError as exc:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.warning("Gemini unavailable for user %s: %s", user.telegram_id, exc)
        raise HTTPException(
            status_code=503,
            detail="AI model is temporarily overloaded. Please try again in a moment.",
        )
    except Exception as exc:
        release_rate_limit(user.telegram_id, bucket="analyze")
        logger.error("Food analysis failed for user %s: %s", user.telegram_id, exc)
        raise HTTPException(status_code=500, detail="Food analysis failed.")

    return {"transcript": transcript}


@router.post("/log")
async def create_log(body: FoodLogIn, user: User = Depends(get_current_user)):
    photo_key = body.photo_key

    # Копирование фото из другой записи (для repeat-with-photo)
    if not photo_key and body.copy_photo_from_log_id is not None:
        source_log = await FoodLog.get_or_none(
            id=body.copy_photo_from_log_id, user_id=user.telegram_id
        )
        if source_log and source_log.photo_url:
            photo_key = source_log.photo_url  # photo_url хранит B2 key

    return await _create_log_with_items(
        user,
        body.log_date,
        body.items,
        photo_key=photo_key,
        meal_name=body.meal_name,
    )


@router.put("/{log_id}")
async def update_log(
    log_id: int,
    body: FoodLogUpdate,
    user: User = Depends(get_current_user),
):
    """
    Правка уже залогированной записи (например, ИИ ошибся в порции/КБЖУ).

    items полностью заменяются (как и раньше), но привязанные WaterLog-записи
    больше не пересоздаются с нуля — сопоставляются со старыми по имени
    блюда и обновляются на месте: сохраняются logged_at и notes, меняется
    только amount_ml и привязка к новому FoodItem.
    """
    food_log = await FoodLog.get_or_none(id=log_id, user_id=user.telegram_id)
    if not food_log:
        raise HTTPException(status_code=404, detail="Log not found")
    if not body.items:
        raise HTTPException(status_code=422, detail="At least one item is required")

    # Захватываем существующую авто-воду ДО замены items — только так можно
    # сопоставить её со старыми именами блюд, пока они ещё не удалены.
    old_water_logs = await WaterLog.filter(
        food_log_id=log_id, food_item_id__isnull=False
    ).prefetch_related("food_item")
    old_water_by_name: dict[str, WaterLog] = {
        wl.food_item.food_name: wl for wl in old_water_logs if wl.food_item
    }

    # Атомарная замена: удаляем все старые items и создаём новые
    await FoodItem.filter(food_log_id=log_id).delete()
    new_items: list[FoodItem] = []
    for item in body.items:
        new_items.append(
            await FoodItem.create(
                food_log_id=log_id,
                food_name=item.food_name,
                portion_g=Decimal(str(item.portion_g)),
                calories=item.calories,
                protein_g=Decimal(str(item.protein_g)),
                fat_g=Decimal(str(item.fat_g)),
                carbs_g=Decimal(str(item.carbs_g)),
                fiber_g=Decimal(str(item.fiber_g)),
                sugar_g=Decimal(str(item.sugar_g)),
                water_ml=item.water_ml,
            )
        )

    await _recalc_totals(food_log)

    # Если после правки в записи остался ровно один компонент — meal_name
    # должен стать названием этого единственного продукта, а не оставаться
    # тем, что ИИ придумал для изначально многосоставного приёма пищи.
    # Если items несколько — обновляем meal_name только если фронт явно его
    # прислал, иначе не трогаем то, что уже сохранено.
    if len(body.items) == 1:
        new_meal_name = body.items[0].food_name
        await FoodLog.filter(id=log_id).update(meal_name=new_meal_name)
    elif body.meal_name is not None:
        await FoodLog.filter(id=log_id).update(meal_name=body.meal_name)

    # Открепление фото — та же логика reference counting, что в delete_log:
    # физически удаляем из B2 только если ни одна другая запись на него
    # больше не ссылается (общий photo_key мог появиться через copy).
    if body.remove_photo and food_log.photo_url:
        still_referenced = (
            await FoodLog.filter(user_id=user.telegram_id, photo_url=food_log.photo_url)
            .exclude(id=log_id)
            .exists()
        )
        if not still_referenced:
            await delete_food_photo(food_log.photo_url)
        await FoodLog.filter(id=log_id).update(photo_url=None)

    await food_log.refresh_from_db()

    # Синхронизация авто-воды: обновляем совпавшие по имени записи на месте
    # (не трогая logged_at/notes), создаём новые для блюд, которых раньше не
    # было, удаляем осиротевшие (блюдо переименовано/удалено/вода обнулилась).
    for new_item in new_items:
        if new_item.water_ml <= 0:
            continue
        existing = old_water_by_name.pop(new_item.food_name, None)
        if existing:
            existing.amount_ml = new_item.water_ml
            existing.food_item_id = new_item.id
            await existing.save()
        else:
            try:
                await WaterLog.create(
                    user_id=user.telegram_id,
                    log_date=food_log.log_date,
                    amount_ml=new_item.water_ml,
                    food_log_id=log_id,
                    food_item_id=new_item.id,
                )
            except Exception:
                logger.exception("auto water log failed for user %s", user.telegram_id)

    for leftover in old_water_by_name.values():
        await leftover.delete()

    # Изменение калорий задним числом может повлиять на дневную цель
    try:
        await _maybe_sync_streak(user, food_log.log_date)
    except Exception:
        logger.exception("streak resync failed for user %s", user.telegram_id)

    items_data = await FoodItemSchema.from_queryset(FoodItem.filter(food_log_id=log_id))
    log_dict = (await FoodLogSchema.from_tortoise_orm(food_log)).model_dump()

    return {
        "log": {**log_dict, "photo_url": await get_photo_url(food_log.photo_url)},
        "items": [i.model_dump() for i in items_data],
    }


class VisibilityUpdate(BaseModel):
    is_public: bool


@router.patch("/{log_id}/visibility")
async def update_log_visibility(
    log_id: int, body: VisibilityUpdate, user: User = Depends(get_current_user)
):
    updated = await FoodLog.filter(id=log_id, user_id=user.telegram_id).update(
        is_public=body.is_public
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"ok": True, "is_public": body.is_public}


@router.get("/search")
async def search_food_history(
    q: str = Query(..., min_length=1, max_length=100),
    user: User = Depends(get_current_user),
):
    items = (
        await FoodItem.filter(
            food_log__user_id=user.telegram_id, food_name__icontains=q
        )
        .order_by("-food_log__logged_at")
        .limit(50)
        .prefetch_related("food_log")
        .all()
    )

    seen: set[str] = set()
    results = []
    for item in items:
        key = item.food_name.lower()
        if key in seen:
            continue
        seen.add(key)
        photo_url = await get_photo_url(item.food_log.photo_url)
        results.append(
            {
                "food_name": item.food_name,
                "portion_g": float(item.portion_g),
                "calories": item.calories,
                "protein_g": float(item.protein_g),
                "fat_g": float(item.fat_g),
                "carbs_g": float(item.carbs_g),
                "fiber_g": float(item.fiber_g),
                "sugar_g": float(item.sugar_g),
                "water_ml": item.water_ml,
                "photo_url": photo_url,
            }
        )
        if len(results) >= 15:
            break

    return {"results": results}


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
            "water_ml": sum(l["total_water_ml"] for l in result),
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
        # Ключ в B2 мог быть скопирован в другую запись через
        # copy_photo_from_log_id (см. CopyMealSheet / create_log).
        # Физически удаляем файл из B2 только если ни одна ДРУГАЯ
        # запись пользователя больше на него не ссылается — иначе
        # просто отвязываем текущий лог, не трогая storage.
        still_referenced = (
            await FoodLog.filter(user_id=user.telegram_id, photo_url=food_log.photo_url)
            .exclude(id=log_id)
            .exists()
        )

        if not still_referenced:
            await delete_food_photo(food_log.photo_url)

    # Удаляем автоматически созданные записи воды, привязанные к этой еде.
    # Ручные записи (food_log_id=NULL) остаются нетронутыми.
    await WaterLog.filter(food_log_id=log_id, user_id=user.telegram_id).delete()

    deleted_log_date = food_log.log_date
    await FoodLog.filter(id=log_id).delete()

    try:
        await _maybe_sync_streak(user, deleted_log_date)
    except Exception:
        logger.exception("streak uncredit failed for user %s", user.telegram_id)

    return {"deleted": True}
