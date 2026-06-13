"""
GET  /api/quests              — активные квесты пользователя
POST /api/quests/generate     — сгенерировать новые квесты (раз в неделю)
POST /api/quests/expire       — пометить просроченные как failed
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from .utils import get_current_user, check_rate_limit
from db import User, Quest, QuestSchema, UserProfile, DailyGoal
from ai.services.quest_generator import generate_weekly_quests

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/quests", tags=["quests"])

MAX_ACTIVE_QUESTS = 6  # Максимум 2 набора по 3
MAX_GENERATE_PER_MINUTE = 2


@router.get("")
async def get_active_quests(user: User = Depends(get_current_user)):
    """Активные квесты + недавно выполненные (для показа в UI)."""
    quests = await Quest.filter(user_id=user.telegram_id, status="active").all()
    return [(await QuestSchema.from_tortoise_orm(q)).model_dump() for q in quests]


@router.post("/generate")
async def generate_quests(user: User = Depends(get_current_user)):
    """
    Генерирует 3 новых квеста через Gemini.
    Вызывай с клиента раз в неделю (или при истечении всех квестов).

    Защита от дубликатов: если уже есть >= MAX_ACTIVE_QUESTS активных — 409.
    """
    check_rate_limit(user.telegram_id, bucket="quests", max_per_minute=MAX_GENERATE_PER_MINUTE)

    # Проверяем количество активных квестов
    active_count = await Quest.filter(
        user_id=user.telegram_id, status="active"
    ).count()
    if active_count >= MAX_ACTIVE_QUESTS:
        raise HTTPException(
            status_code=409,
            detail=f"Already have {active_count} active quests (max {MAX_ACTIVE_QUESTS}). "
            f"Wait for them to expire or complete.",
        )

    profile = await UserProfile.get_or_none(user_id=user.telegram_id)
    goal = await DailyGoal.get_or_none(user_id=user.telegram_id)

    profile_summary = {
        "goal_type": profile.goal_type if profile else "maintain",
        "activity_level": profile.activity_level if profile else "moderate",
        "current_streak": user.current_streak,
        "target_calories": goal.calories if goal else 2000,
    }

    quest_list = await generate_weekly_quests(profile_summary)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    created = []
    for q in quest_list:
        quest = await Quest.create(
            user_id=user.telegram_id,
            quest_key=q["quest_key"],
            title=q["title"],
            description=q["description"],
            icon=q.get("icon", "🎯"),
            target_value=q["target_value"],
            expires_at=expires_at,
        )
        created.append((await QuestSchema.from_tortoise_orm(quest)).model_dump())

    return {"quests": created}


@router.post("/expire")
async def expire_quests(user: User = Depends(get_current_user)):
    """
    Помечает просроченные активные квесты как failed.

    Вызывается клиентом при входе в приложение или при открытии
    экрана квестов — лёгкий запрос, не вызывает Gemini.
    """
    now = datetime.now(timezone.utc)
    expired = await Quest.filter(
        user_id=user.telegram_id,
        status=Quest.STATUS_ACTIVE,
        expires_at__lt=now,
    ).update(status=Quest.STATUS_FAILED)

    return {"expired_count": expired}
