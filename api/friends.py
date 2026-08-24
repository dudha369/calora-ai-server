"""
GET    /api/friends              — список друзей + входящие/исходящие заявки
POST   /api/friends/request      — отправить заявку по username
POST   /api/friends/{id}/respond — принять/отклонить входящую заявку
DELETE /api/friends/{id}         — отменить исходящую заявку или удалить из друзей
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .utils import get_current_user, check_rate_limit
from db import User, Friendship

router = APIRouter(prefix="/api/friends", tags=["friends"])

MAX_REQUESTS_PER_MINUTE = 10


def _public_user(u: User) -> dict:
    return {
        "telegram_id": u.telegram_id,
        "full_name": u.full_name,
        "username": u.username,
    }


class FriendRequestIn(BaseModel):
    username: str


class RespondIn(BaseModel):
    accept: bool


@router.get("")
async def list_friends(user: User = Depends(get_current_user)):
    accepted = (
        await Friendship.filter(status=Friendship.STATUS_ACCEPTED)
        .filter(user_id=user.telegram_id)
        .prefetch_related("friend")
    )
    accepted_reverse = await Friendship.filter(
        status=Friendship.STATUS_ACCEPTED, friend_id=user.telegram_id
    ).prefetch_related("user")
    incoming = await Friendship.filter(
        status=Friendship.STATUS_PENDING, friend_id=user.telegram_id
    ).prefetch_related("user")
    outgoing = await Friendship.filter(
        status=Friendship.STATUS_PENDING, user_id=user.telegram_id
    ).prefetch_related("friend")

    return {
        "friends": [
            {"friendship_id": f.id, "user": _public_user(f.friend)} for f in accepted
        ]
        + [
            {"friendship_id": f.id, "user": _public_user(f.user)}
            for f in accepted_reverse
        ],
        "incoming": [
            {"friendship_id": f.id, "user": _public_user(f.user)} for f in incoming
        ],
        "outgoing": [
            {"friendship_id": f.id, "user": _public_user(f.friend)} for f in outgoing
        ],
    }


@router.post("/request")
async def request_friend(body: FriendRequestIn, user: User = Depends(get_current_user)):
    check_rate_limit(
        user.telegram_id,
        bucket="friend_request",
        max_per_minute=MAX_REQUESTS_PER_MINUTE,
    )

    handle = body.username.strip().lstrip("@")
    target = await User.get_or_none(username__iexact=handle)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.telegram_id == user.telegram_id:
        raise HTTPException(status_code=400, detail="Cannot add yourself")

    existing = await Friendship.get_or_none(
        user_id=user.telegram_id, friend_id=target.telegram_id
    )
    if existing:
        raise HTTPException(status_code=400, detail="Request already exists")

    # Взаимный мэтч: если target уже отправил(а) нам pending-запрос —
    # сразу подтверждаем его, не создавая вторую строку.
    reverse = await Friendship.get_or_none(
        user_id=target.telegram_id, friend_id=user.telegram_id
    )
    if reverse and reverse.status == Friendship.STATUS_PENDING:
        reverse.status = Friendship.STATUS_ACCEPTED
        await reverse.save()
        return {"status": "accepted"}

    await Friendship.create(user_id=user.telegram_id, friend_id=target.telegram_id)
    return {"status": "pending"}


@router.post("/{friendship_id}/respond")
async def respond_to_request(
    friendship_id: int, body: RespondIn, user: User = Depends(get_current_user)
):
    friendship = await Friendship.get_or_none(
        id=friendship_id, friend_id=user.telegram_id, status=Friendship.STATUS_PENDING
    )
    if not friendship:
        raise HTTPException(status_code=404, detail="Request not found")

    if body.accept:
        friendship.status = Friendship.STATUS_ACCEPTED
        await friendship.save()
        return {"status": "accepted"}

    await friendship.delete()
    return {"status": "declined"}


@router.delete("/{friendship_id}")
async def remove_friendship(friendship_id: int, user: User = Depends(get_current_user)):
    """Отменяет исходящую заявку ИЛИ удаляет из друзей — работает с любой
    стороны отношения (user или friend), т.к. строка не дублируется."""
    deleted = (
        await Friendship.filter(id=friendship_id)
        .filter(user_id=user.telegram_id)
        .delete()
        or await Friendship.filter(
            id=friendship_id, friend_id=user.telegram_id
        ).delete()
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Friendship not found")
    return {"ok": True}
