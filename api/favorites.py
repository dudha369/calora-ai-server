"""
GET    /api/favorites        — список избранных блюд пользователя
POST   /api/favorites        — сохранить блюдо в избранное (копия items,
                                независима от исходного FoodLog)
DELETE /api/favorites/{id}   — удалить из избранного
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .utils import get_current_user
from db import (
    User,
    FavoriteMeal,
    FavoriteMealItem,
    FavoriteMealSchema,
    FavoriteMealItemSchema,
)

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class FavoriteItemIn(BaseModel):
    food_name: str
    portion_g: float
    calories: int
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    water_ml: int = 0


class FavoriteMealIn(BaseModel):
    meal_name: str
    items: list[FavoriteItemIn]


async def _serialize(favorite: FavoriteMeal) -> dict:
    items = await FavoriteMealItemSchema.from_queryset(
        FavoriteMealItem.filter(favorite_meal_id=favorite.id)
    )
    data = (await FavoriteMealSchema.from_tortoise_orm(favorite)).model_dump()
    return {**data, "items": [i.model_dump() for i in items]}


@router.get("")
async def list_favorites(user: User = Depends(get_current_user)):
    favs = await FavoriteMeal.filter(user_id=user.telegram_id).all()
    return [await _serialize(f) for f in favs]


@router.post("")
async def create_favorite(body: FavoriteMealIn, user: User = Depends(get_current_user)):
    if not body.items:
        raise HTTPException(status_code=422, detail="At least one item is required")

    favorite = await FavoriteMeal.create(
        user_id=user.telegram_id,
        meal_name=body.meal_name,
    )
    for item in body.items:
        await FavoriteMealItem.create(
            favorite_meal_id=favorite.id,
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

    return await _serialize(favorite)


@router.delete("/{favorite_id}")
async def delete_favorite(favorite_id: int, user: User = Depends(get_current_user)):
    favorite = await FavoriteMeal.get_or_none(id=favorite_id, user_id=user.telegram_id)
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    await favorite.delete()
    return {"deleted": True}
