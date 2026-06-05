from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class FoodItem(Model):
    """
    Отдельное блюдо/продукт внутри FoodLog.
    ИИ может найти несколько блюд на одном фото — каждое отдельной записью.
    После добавления/удаления → пересчитывай total_* в родительском FoodLog.
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

    class Meta:
        table = "food_items"


FoodItemSchema = pydantic_model_creator(FoodItem, name="FoodItem")
