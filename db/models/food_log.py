from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class FoodLog(Model):
    """
    ...(докстринг без изменений)...
    total_water_ml — сумма FoodItem.water_ml по этому логу. Пересчитывается
    в api/food.py._recalc_totals по тому же паттерну, что total_fiber_g/
    total_sugar_g. Нужен, чтобы показать в UI "сколько воды дал этот приём
    пищи" без похода за FoodItem-ами (FoodLogCard, FoodLogModal).
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="food_logs", on_delete=fields.CASCADE
    )

    log_date = fields.DateField()
    logged_at = fields.DatetimeField(auto_now_add=True)
    photo_url = fields.TextField(null=True)
    meal_name = fields.CharField(max_length=200, null=True)

    total_calories = fields.SmallIntField(default=0)
    total_protein_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_fat_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_carbs_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_fiber_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_sugar_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_water_ml = fields.SmallIntField(default=0)

    class Meta:
        table = "food_logs"
        indexes = [("user_id", "log_date")]
        ordering = ["-logged_at"]


FoodLogSchema = pydantic_model_creator(FoodLog, name="FoodLog")
