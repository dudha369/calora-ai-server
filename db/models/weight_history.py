from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WeightHistory(Model):
    """
    История взвешиваний для графика прогресса.
    Запись добавляется автоматически при обновлении weight_kg в UserProfile.

    log_date   — дата взвешивания в локальном времени пользователя
                 (аналогично FoodLog.log_date и WaterLog.log_date).
                 Позволяет записать вес за вчера (взвесился утром, записал вечером).
    recorded_at — UTC-момент создания записи (auto).
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="weight_history", on_delete=fields.CASCADE
    )
    weight_kg = fields.DecimalField(max_digits=5, decimal_places=1)
    log_date = fields.DateField(null=True)
    recorded_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "weight_history"
        ordering = ["-recorded_at"]


WeightHistorySchema = pydantic_model_creator(WeightHistory, name="WeightHistory")
