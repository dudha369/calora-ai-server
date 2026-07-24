from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WaterLog(Model):
    """
    Запись воды пользователя.

    food_log — nullable FK на FoodLog. Покрывает оба сценария привязки:
               • авто-создание при логировании еды с напитками
                 (см. api/food.py._maybe_log_water);
               • ручная привязка/отвязка пользователем через
                 PATCH /api/water/{id} (см. WaterLogModal на фронте).
               NULL = запись ни к какому приёму пищи не привязана.

    notes — свободная заметка пользователя к записи. Независима от food_log —
            можно иметь заметку без привязки к еде и наоборот.

    Отображаемое имя записи (когда она привязана к еде) больше не хранится
    здесь отдельным полем — раньше для этого было source_label, но это был
    просто снэпшот FoodLog.meal_name/food_name на момент создания, который
    расходился с реальным блюдом при его переименовании или удалении. Теперь
    имя всегда берётся напрямую из FoodLog при сериализации (см. api/water.py).

    Жизненный цикл:
      • food_log_id IS NULL     → независима, удаляется только пользователем
      • food_log_id IS NOT NULL → удаляется вместе с этим приёмом пищи
        (см. delete_log в api/food.py)
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
    notes = fields.TextField(null=True)

    class Meta:
        table = "water_logs"
        indexes = [("user_id", "log_date")]
        ordering = ["-logged_at"]


WaterLogSchema = pydantic_model_creator(WaterLog, name="WaterLog")
