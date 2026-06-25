from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WaterLog(Model):
    """
    Запись воды пользователя.

    food_log — nullable FK на FoodLog. Заполняется только для записей,
               созданных автоматически при логировании еды с напитками.
               NULL = ручная запись пользователя (через /api/water).

    Жизненный цикл:
      • food_log_id IS NULL  → независима, удаляется только пользователем
      • food_log_id IS NOT NULL → привязана к еде, удаляется вместе с ней
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="water_logs", on_delete=fields.CASCADE
    )
    food_log = fields.ForeignKeyField(
        "models.FoodLog",
        related_name="auto_water_logs",
        on_delete=fields.SET_NULL,
        null=True,
    )

    log_date = fields.DateField()
    logged_at = fields.DatetimeField(auto_now_add=True)
    amount_ml = fields.SmallIntField()

    class Meta:
        table = "water_logs"
        indexes = [("user_id", "log_date")]
        ordering = ["-logged_at"]


WaterLogSchema = pydantic_model_creator(WaterLog, name="WaterLog")
