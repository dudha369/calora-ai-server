"""
GET /api/feed?limit=20&offset=0 — публичные приёмы пищи друзей,
    отсортированные по времени логирования (новые первыми).
"""

from fastapi import APIRouter, Depends, Query

from .utils import get_current_user
from db import User, Friendship, FoodLog, FoodItem
from services.storage import get_photo_url

router = APIRouter(prefix="/api/feed", tags=["feed"])


async def _friend_ids(user_id: int) -> list[int]:
    forward = await Friendship.filter(
        user_id=user_id, status=Friendship.STATUS_ACCEPTED
    ).values_list("friend_id", flat=True)
    backward = await Friendship.filter(
        friend_id=user_id, status=Friendship.STATUS_ACCEPTED
    ).values_list("user_id", flat=True)
    return list(set(forward) | set(backward))


@router.get("")
async def get_feed(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    friend_ids = await _friend_ids(user.telegram_id)
    if not friend_ids:
        return {"items": [], "has_more": False}

    logs = (
        await FoodLog.filter(user_id__in=friend_ids, is_public=True)
        .order_by("-logged_at")
        .offset(offset)
        .limit(limit + 1)  # +1 чтобы дёшево узнать has_more без отдельного count()
        .prefetch_related("items")
    )
    has_more = len(logs) > limit
    logs = logs[:limit]

    authors = {u.telegram_id: u for u in await User.filter(telegram_id__in=friend_ids)}

    items = []
    for log in logs:
        author = authors.get(log.user_id)
        items.append(
            {
                "id": log.id,
                "user": (
                    {
                        "telegram_id": author.telegram_id,
                        "full_name": author.full_name,
                        "username": author.username,
                    }
                    if author
                    else None
                ),
                "log_date": log.log_date.isoformat(),
                "logged_at": log.logged_at.isoformat(),
                "photo_url": await get_photo_url(log.photo_url),
                "meal_name": log.meal_name,
                "total_calories": log.total_calories,
                "total_protein_g": float(log.total_protein_g),
                "total_fat_g": float(log.total_fat_g),
                "total_carbs_g": float(log.total_carbs_g),
                "items": [
                    {"food_name": i.food_name, "portion_g": float(i.portion_g)}
                    for i in log.items
                ],
            }
        )

    return {"items": items, "has_more": has_more}
