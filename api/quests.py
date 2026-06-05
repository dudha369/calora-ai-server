"""
GET  /api/quests         — активные квесты пользователя
POST /api/quests/generate — сгенерировать новые квесты (вызывать раз в неделю)
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from aiogram.utils.web_app import WebAppInitData

from .utils import auth, get_or_create_user
from db import Quest, QuestSchema, UserProfile, DailyGoal
from ai.services.quest_generator import generate_weekly_quests

router = APIRouter(prefix="/api/quests", tags=["quests"])


@router.get("")
async def get_active_quests(auth_data: WebAppInitData = Depends(auth)):
    """Активные квесты + недавно выполненные (для показа в UI)."""
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
    )
    quests = await Quest.filter(user_id=user.telegram_id, status="active").all()
    return [(await QuestSchema.from_tortoise_orm(q)).model_dump() for q in quests]


@router.post("/generate")
async def generate_quests(auth_data: WebAppInitData = Depends(auth)):
    """
    Генерирует 3 новых квеста через Gemini.
    Вызывай с клиента раз в неделю (или при истечении всех квестов).
    """
    user = await get_or_create_user(
        auth_data.user.id, auth_data.user.first_name or "Unknown"
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
