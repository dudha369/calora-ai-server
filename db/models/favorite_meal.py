from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class FavoriteMeal(Model):
    """
    Избранный приём пищи — сохранённый шаблон для быстрого повторного
    логирования (см. api/favorites.py). Структура зеркалит FoodLog/FoodItem:
    один FavoriteMeal содержит несколько FavoriteMealItem.

    Копия items независима от исходного FoodLog — удаление лога не трогает
    избранное, и наоборот. Фото сознательно не хранится: пришлось бы тащить
    reference-counting логику B2 (см. FoodLog.photo_url) в третье место —
    не стоит того ради избранного.
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="favorite_meals", on_delete=fields.CASCADE
    )
    meal_name = fields.CharField(max_length=200)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "favorite_meals"
        ordering = ["-created_at"]


class FavoriteMealItem(Model):
    """Отдельное блюдо внутри FavoriteMeal — зеркалит FoodItem."""

    favorite_meal = fields.ForeignKeyField(
        "models.FavoriteMeal", related_name="items", on_delete=fields.CASCADE
    )

    food_name = fields.CharField(max_length=200)
    portion_g = fields.DecimalField(max_digits=6, decimal_places=1)
    calories = fields.SmallIntField()
    protein_g = fields.DecimalField(max_digits=5, decimal_places=1)
    fat_g = fields.DecimalField(max_digits=5, decimal_places=1)
    carbs_g = fields.DecimalField(max_digits=5, decimal_places=1)
    fiber_g = fields.DecimalField(max_digits=5, decimal_places=1, default=0)
    sugar_g = fields.DecimalField(max_digits=5, decimal_places=1, default=0)
    water_ml = fields.SmallIntField(default=0)

    class Meta:
        table = "favorite_meal_items"


FavoriteMealSchema = pydantic_model_creator(FavoriteMeal, name="FavoriteMeal")
FavoriteMealItemSchema = pydantic_model_creator(
    FavoriteMealItem, name="FavoriteMealItem"
)
