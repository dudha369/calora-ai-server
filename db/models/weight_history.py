from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WeightHistory(Model):
    """
    История взвешиваний для графика прогресса и списка на WeightPage.
    Запись создаётся через POST /api/weight (см. api/weight.py), который
    заодно обновляет UserProfile.weight_kg и пересчитывает DailyGoal —
    аналогично прежнему побочному эффекту PUT /api/profile при смене веса,
    но явным отдельным эндпоинтом.

    log_date   — дата взвешивания в локальном времени пользователя
                 (аналогично FoodLog.log_date и WaterLog.log_date).
                 Позволяет записать вес за вчера (взвесился утром, записал вечером).
    note       — свободная заметка к записи (например "после тренировки").
    recorded_at — UTC-момент создания записи (auto).
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="weight_history", on_delete=fields.CASCADE
    )
    weight_kg = fields.DecimalField(max_digits=5, decimal_places=1)
    log_date = fields.DateField(null=True)
    note = fields.CharField(max_length=200, null=True)
    recorded_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "weight_history"
        ordering = ["-recorded_at"]


WeightHistorySchema = pydantic_model_creator(WeightHistory, name="WeightHistory")
