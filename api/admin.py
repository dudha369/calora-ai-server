"""
Admin API — доступно только для ADMIN_TELEGRAM_ID.

GET    /api/admin/config        — проверка is_admin
GET    /api/admin/dashboard     — статистика
GET    /api/admin/users         — список пользователей
GET    /api/admin/users/{id}    — карточка пользователя
POST   /api/admin/users/{id}/reset   — сброс профиля
DELETE /api/admin/users/{id}         — удаление аккаунта
GET    /api/admin/settings      — feature flags
PUT    /api/admin/settings      — обновить feature flags
GET    /api/admin/whitelist          — обогащённый whitelist с именами
POST   /api/admin/whitelist/{id}     — добавить в whitelist
DELETE /api/admin/whitelist/{id}     — убрать из whitelist
GET    /api/admin/users/{id}/avatar  — аватарка пользователя (proxy)
POST   /api/admin/broadcast          — отправить рассылку
GET    /api/admin/broadcasts         — история рассылок
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from tortoise.expressions import Q

from .utils import get_current_user
from bot_instance import bot
from config import config
from db import (
    User,
    UserProfile,
    UserProfileSchema,
    DailyGoal,
    DailyGoalSchema,
    OnboardingDraft,
    FoodLog,
    FoodItem,
    WaterLog,
    Quest,
)
from db.models.app_settings import AppSettings
from db.models.broadcast import Broadcast
from services.storage import delete_food_photos

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Auth dependency ──────────────────────────────────────────────────────────


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """Проверяет что текущий пользователь — админ."""
    if user.telegram_id != config.ADMIN_TELEGRAM_ID:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ── Config ───────────────────────────────────────────────────────────────────


@router.get("/config")
async def admin_config(user: User = Depends(get_current_user)):
    """Возвращает is_admin для текущего пользователя (не требует админа)."""
    return {"is_admin": user.telegram_id == config.ADMIN_TELEGRAM_ID}


# ── Dashboard ────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def dashboard(_: User = Depends(get_admin_user)):
    now = datetime.now(timezone.utc)
    today = now.date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Базовые счётчики
    total_users = await User.all().count()
    new_today = await User.filter(created_at__gte=today).count()
    new_week = await User.filter(created_at__gte=week_ago).count()
    new_month = await User.filter(created_at__gte=month_ago).count()

    # Онбординг
    completed_onboarding = await UserProfile.all().count()
    stuck_onboarding = await OnboardingDraft.all().count()

    # Активность сегодня (уникальные юзеры с food_log или water_log)
    food_active = await FoodLog.filter(log_date=today).values_list(
        "user_id", flat=True
    )
    water_active = await WaterLog.filter(log_date=today).values_list(
        "user_id", flat=True
    )
    dau = len(set(food_active) | set(water_active))

    # Food stats
    total_food_logs = await FoodLog.all().count()
    total_photo_scans = await FoodLog.filter(photo_url__isnull=False).count()

    # Квесты
    quests_active = await Quest.filter(status="active").count()
    quests_done = await Quest.filter(status="done").count()
    quests_failed = await Quest.filter(status="failed").count()

    # Регистрации по дням (30 дней)
    signups_by_day = []
    for i in range(30):
        d = today - timedelta(days=29 - i)
        d_next = d + timedelta(days=1)
        cnt = await User.filter(created_at__gte=d, created_at__lt=d_next).count()
        signups_by_day.append({"date": d.isoformat(), "count": cnt})

    # DAU тренд (7 дней)
    dau_trend = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        fa = await FoodLog.filter(log_date=d).values_list(
            "user_id", flat=True
        )
        wa = await WaterLog.filter(log_date=d).values_list(
            "user_id", flat=True
        )
        dau_trend.append({"date": d.isoformat(), "dau": len(set(fa) | set(wa))})

    # Онбординг воронка (по шагам)
    funnel = []
    for step in range(0, 11):
        cnt = await OnboardingDraft.filter(step=step).count()
        funnel.append({"step": step, "count": cnt})

    return {
        "total_users": total_users,
        "new_today": new_today,
        "new_week": new_week,
        "new_month": new_month,
        "completed_onboarding": completed_onboarding,
        "stuck_onboarding": stuck_onboarding,
        "onboarding_rate": round(
            completed_onboarding / total_users * 100, 1
        )
        if total_users
        else 0,
        "dau": dau,
        "total_food_logs": total_food_logs,
        "total_photo_scans": total_photo_scans,
        "quests": {
            "active": quests_active,
            "done": quests_done,
            "failed": quests_failed,
        },
        "signups_by_day": signups_by_day,
        "dau_trend": dau_trend,
        "onboarding_funnel": funnel,
    }


# ── Users ────────────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(
    search: str = "",
    filter: str = "all",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: User = Depends(get_admin_user),
):
    qs = User.all()

    # Поиск
    if search.strip():
        s = search.strip()
        if s.isdigit():
            qs = qs.filter(telegram_id=int(s))
        else:
            qs = qs.filter(
                Q(full_name__icontains=s) | Q(username__icontains=s)
            )

    # Фильтры
    if filter == "onboarded":
        onboarded_ids = await UserProfile.all().values_list("user_id", flat=True)
        qs = qs.filter(telegram_id__in=onboarded_ids)
    elif filter == "stuck":
        stuck_ids = await OnboardingDraft.all().values_list("user_id", flat=True)
        qs = qs.filter(telegram_id__in=stuck_ids)
    elif filter == "active_today":
        today = datetime.now(timezone.utc).date()
        fa = await FoodLog.filter(log_date=today).values_list(
            "user_id", flat=True
        )
        wa = await WaterLog.filter(log_date=today).values_list(
            "user_id", flat=True
        )
        active_ids = set(fa) | set(wa)
        qs = qs.filter(telegram_id__in=list(active_ids))

    total = await qs.count()
    offset = (page - 1) * per_page
    users = await qs.order_by("-created_at").offset(offset).limit(per_page)

    # Enrich
    whitelist_ids = _get_whitelist_ids()
    onboarded_ids_set = set(
        await UserProfile.all().values_list("user_id", flat=True)
    )

    result = []
    for u in users:
        result.append({
            "telegram_id": u.telegram_id,
            "full_name": u.full_name,
            "username": u.username,
            "language_code": u.language_code,
            "current_streak": u.current_streak,
            "max_streak": u.max_streak,
            "quests_completed": u.quests_completed,
            "created_at": u.created_at.isoformat(),
            "onboarded": u.telegram_id in onboarded_ids_set,
            "in_whitelist": u.telegram_id in whitelist_ids,
        })

    return {
        "users": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    _: User = Depends(get_admin_user),
):
    user = await User.get_or_none(telegram_id=user_id)
    if not user:
        raise HTTPException(404, "User not found")

    profile = await UserProfile.get_or_none(user_id=user_id)
    profile_data = (
        (await UserProfileSchema.from_tortoise_orm(profile)).model_dump()
        if profile
        else None
    )

    goal = await DailyGoal.get_or_none(user_id=user_id)
    goal_data = (
        (await DailyGoalSchema.from_tortoise_orm(goal)).model_dump()
        if goal
        else None
    )

    # Последние 10 записей еды
    food_logs = await FoodLog.filter(user_id=user_id).order_by("-logged_at").limit(10)
    food_data = []
    for fl in food_logs:
        items = await FoodItem.filter(food_log_id=fl.id).all()
        food_data.append({
            "id": fl.id,
            "log_date": fl.log_date.isoformat(),
            "photo_url": fl.photo_url,
            "total_calories": fl.total_calories,
            "total_protein_g": float(fl.total_protein_g),
            "total_fat_g": float(fl.total_fat_g),
            "total_carbs_g": float(fl.total_carbs_g),
            "items": [
                {
                    "food_name": item.food_name,
                    "portion_g": float(item.portion_g),
                    "calories": item.calories,
                }
                for item in items
            ],
        })

    # Квесты
    quests = await Quest.filter(user_id=user_id).order_by("-expires_at").limit(5)
    quests_data = [
        {
            "title": q.title,
            "status": q.status,
            "current_value": float(q.current_value),
            "target_value": float(q.target_value),
            "icon": q.icon,
        }
        for q in quests
    ]

    whitelist_ids = _get_whitelist_ids()

    return {
        "user": {
            "telegram_id": user.telegram_id,
            "full_name": user.full_name,
            "username": user.username,
            "language_code": user.language_code,
            "current_streak": user.current_streak,
            "max_streak": user.max_streak,
            "quests_completed": user.quests_completed,
            "created_at": user.created_at.isoformat(),
            "in_whitelist": user.telegram_id in whitelist_ids,
        },
        "profile": profile_data,
        "goal": goal_data,
        "food_logs": food_data,
        "quests": quests_data,
    }


@router.post("/users/{user_id}/reset")
async def reset_user(user_id: int, _: User = Depends(get_admin_user)):
    """Сбрасывает профиль пользователя (soft-reset на онбординг)."""
    user = await User.get_or_none(telegram_id=user_id)
    if not user:
        raise HTTPException(404, "User not found")

    await UserProfile.filter(user_id=user_id).delete()
    await DailyGoal.filter(user_id=user_id).delete()
    await OnboardingDraft.filter(user_id=user_id).delete()
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, _: User = Depends(get_admin_user)):
    """Полностью удаляет пользователя и все его данные."""
    user = await User.get_or_none(telegram_id=user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Удаляем фото из B2
    photo_keys = await FoodLog.filter(
        user_id=user_id, photo_url__isnull=False
    ).values_list("photo_url", flat=True)
    await delete_food_photos(list(photo_keys))

    await User.filter(telegram_id=user_id).delete()
    return {"ok": True}


# ── Settings ─────────────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(_: User = Depends(get_admin_user)):
    """Читает настройки из config (env) — единый источник правды."""
    return {
        "settings": {
            "whitelist_enabled": str(config.WHITELIST_ENABLED).lower(),
            "whitelist_ids": config.WHITELIST_IDS,
            "maintenance_mode": await AppSettings.get_value("maintenance_mode", "false"),
            "registration_enabled": await AppSettings.get_value("registration_enabled", "true"),
        }
    }


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


_DB_SETTINGS_KEYS = {"maintenance_mode", "registration_enabled"}


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    _: User = Depends(get_admin_user),
):
    for key, value in body.settings.items():
        if key == "whitelist_enabled":
            config.WHITELIST_ENABLED = value.lower() in ("true", "1", "yes")
        elif key == "whitelist_ids":
            config.WHITELIST_IDS = value
        elif key in _DB_SETTINGS_KEYS:
            await AppSettings.set_value(key, value)
        # unknown keys silently ignored
    return {"ok": True}


# ── Whitelist ────────────────────────────────────────────────────────────────


def _get_whitelist_ids() -> set[int]:
    """Читает whitelist IDs из config (тот же источник что api/utils.py)."""
    return config.whitelist_ids


def _save_whitelist_ids(ids: set[int]) -> None:
    """Обновляет whitelist IDs в config runtime."""
    config.WHITELIST_IDS = ",".join(str(i) for i in sorted(ids))


@router.get("/whitelist")
async def get_whitelist(_: User = Depends(get_admin_user)):
    """Обогащённый whitelist — для каждого ID имя, username и наличие в БД."""
    ids = _get_whitelist_ids()
    result = []

    for tid in sorted(ids):
        entry: dict = {"telegram_id": tid, "full_name": None, "username": None, "in_db": False}
        # Пробуем найти в БД
        user = await User.get_or_none(telegram_id=tid)
        if user:
            entry["full_name"] = user.full_name
            entry["username"] = user.username
            entry["in_db"] = True
        else:
            # Fallback: спрашиваем Telegram Bot API
            try:
                chat = await bot.get_chat(tid)
                entry["full_name"] = " ".join(
                    filter(None, [chat.first_name, chat.last_name])
                )
                entry["username"] = chat.username
            except Exception:
                entry["full_name"] = str(tid)
        result.append(entry)

    return {"whitelist": result, "enabled": config.WHITELIST_ENABLED}


http_session: Optional[aiohttp.ClientSession] = None


async def get_http_session() -> Optional[ClientSession]:
    global http_session
    if http_session is None:
        http_session = aiohttp.ClientSession()
    return http_session


@router.get("/users/{user_id}/avatar")
async def get_user_avatar(
        user_id: int,
        _: User = Depends(get_admin_user),
        session: aiohttp.ClientSession = Depends(get_http_session)
):
    """Проксирует аватарку пользователя из Telegram."""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos.photos:
            raise HTTPException(status_code=404, detail="No avatar")

        # Индекс 0 — самый маленький размер (быстрее скачается)
        file_id = photos.photos[0][0].file_id
        file = await bot.get_file(file_id)

        url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN.get_secret_value()}/{file.file_path}"

        async with session.get(url) as resp:
            resp.raise_for_status()  # Проверим, что Телеграм ответил 200 OK
            data = await resp.read()

            return Response(
                content=data,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"},
            )

    except HTTPException:
        # Прокидываем дальше уже сформированные ошибки HTTP
        raise
    except Exception as e:
        # Логируем реальную причину падения
        logger.error(f"Error fetching avatar for user {user_id}: {e}")
        raise HTTPException(status_code=404, detail="Avatar not available")


@router.post("/whitelist/{user_id}")
async def add_to_whitelist(user_id: int, _: User = Depends(get_admin_user)):
    ids = _get_whitelist_ids()
    ids.add(user_id)
    _save_whitelist_ids(ids)
    return {"ok": True, "whitelist_ids": sorted(ids)}


@router.delete("/whitelist/{user_id}")
async def remove_from_whitelist(user_id: int, _: User = Depends(get_admin_user)):
    ids = _get_whitelist_ids()
    ids.discard(user_id)
    _save_whitelist_ids(ids)
    return {"ok": True, "whitelist_ids": sorted(ids)}


# ── Broadcast ────────────────────────────────────────────────────────────────


class BroadcastRequest(BaseModel):
    text: str
    segment: str = "all"  # all | active | inactive | new | not_onboarded
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    preview: bool = False  # если True — шлёт только админу


@router.post("/broadcast")
async def send_broadcast(
    body: BroadcastRequest,
    admin: User = Depends(get_admin_user),
):
    # Определяем получателей
    if body.preview:
        recipients = [admin.telegram_id]
    else:
        recipients = await _get_broadcast_recipients(body.segment)

    if not recipients:
        return {"ok": False, "error": "No recipients"}

    # Создаём запись
    broadcast = await Broadcast.create(
        text=body.text,
        segment=body.segment,
        button_text=body.button_text,
        button_url=body.button_url,
        status="preview" if body.preview else "sending",
        total=len(recipients),
    )

    # Запускаем рассылку в фоне
    asyncio.create_task(
        _do_broadcast(broadcast.id, recipients, body.text, body.button_text, body.button_url)
    )

    return {
        "ok": True,
        "broadcast_id": broadcast.id,
        "recipients": len(recipients),
    }


@router.get("/broadcasts")
async def list_broadcasts(_: User = Depends(get_admin_user)):
    broadcasts = await Broadcast.all().order_by("-created_at").limit(20)
    return {
        "broadcasts": [
            {
                "id": b.id,
                "text": b.text[:100],
                "segment": b.segment,
                "status": b.status,
                "total": b.total,
                "sent": b.sent,
                "failed": b.failed,
                "created_at": b.created_at.isoformat(),
            }
            for b in broadcasts
        ]
    }


async def _get_broadcast_recipients(segment: str) -> list[int]:
    """Возвращает список telegram_id по сегменту."""
    today = datetime.now(timezone.utc).date()

    if segment == "all":
        return await User.all().values_list("telegram_id", flat=True)

    elif segment == "active":
        week_ago = today - timedelta(days=7)
        fa = await FoodLog.filter(log_date__gte=week_ago).values_list(
            "user_id", flat=True
        )
        wa = await WaterLog.filter(log_date__gte=week_ago).values_list(
            "user_id", flat=True
        )
        return list(set(fa) | set(wa))

    elif segment == "inactive":
        week_ago = today - timedelta(days=7)
        active_fa = await FoodLog.filter(
            log_date__gte=week_ago
        ).values_list("user_id", flat=True)
        active_wa = await WaterLog.filter(
            log_date__gte=week_ago
        ).values_list("user_id", flat=True)
        active = set(active_fa) | set(active_wa)
        all_ids = set(await User.all().values_list("telegram_id", flat=True))
        return list(all_ids - active)

    elif segment == "new":
        three_days_ago = today - timedelta(days=3)
        return await User.filter(
            created_at__gte=three_days_ago
        ).values_list("telegram_id", flat=True)

    elif segment == "not_onboarded":
        onboarded = set(
            await UserProfile.all().values_list("user_id", flat=True)
        )
        all_ids = set(await User.all().values_list("telegram_id", flat=True))
        return list(all_ids - onboarded)

    return []


async def _do_broadcast(
    broadcast_id: int,
    recipients: list[int],
    text: str,
    button_text: Optional[str],
    button_url: Optional[str],
) -> None:
    """Фоновая задача рассылки."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    sent = 0
    failed = 0

    reply_markup = None
    if button_text and button_url:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=button_text, url=button_url)]
            ]
        )

    for uid in recipients:
        try:
            await bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast to {uid} failed: {e}")
            failed += 1

        # Rate limit: 30 msg/sec max для Telegram Bot API
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    await Broadcast.filter(id=broadcast_id).update(
        status="done",
        sent=sent,
        failed=failed,
        finished_at=datetime.now(timezone.utc),
    )
