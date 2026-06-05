from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WeightHistory(Model):
    """
    История взвешиваний для графика прогресса.
    Запись добавляется автоматически при обновлении weight_kg в UserProfile.
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="weight_history", on_delete=fields.CASCADE
    )
    weight_kg = fields.DecimalField(max_digits=5, decimal_places=1)
    recorded_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "weight_history"
        ordering = ["-recorded_at"]


WeightHistorySchema = pydantic_model_creator(WeightHistory, name="WeightHistory")
