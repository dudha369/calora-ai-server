from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class FoodItem(Model):
    """
    Отдельное блюдо/продукт внутри FoodLog.

    water_ml — вода/гидратация от этого конкретного блюда/напитка
               (заполняется AI-анализом). Хранится здесь, чтобы при
               повторении записи (repeat) можно было восстановить
               полную картину без дополнительных запросов.
    """

    food_log = fields.ForeignKeyField(
        "models.FoodLog", related_name="items", on_delete=fields.CASCADE
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
        table = "food_items"


FoodItemSchema = pydantic_model_creator(FoodItem, name="FoodItem")
