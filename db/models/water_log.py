from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WaterLog(Model):
    """
    Запись воды пользователя.

    food_log — nullable FK на FoodLog. Покрывает оба сценария привязки:
               • авто-создание при логировании еды с напитками
                 (см. api/food.py._create_auto_water_logs);
               • ручная привязка/отвязка пользователем через
                 PATCH /api/water/{id} (см. WaterLogModal на фронте).
               NULL = запись ни к какому приёму пищи не привязана.

    food_item — nullable FK на конкретное блюдо/напиток внутри food_log,
                если запись создана автоматически из-за конкретного item'а
                (например "Горячий шоколад" внутри приёма пищи, где кроме
                него есть ещё "Омлет"). Позволяет показывать имя именно
                этого блюда, а не название всего приёма пищи целиком
                (см. api/water.py._food_log_summary). При замене items
                на PUT /api/food/{id} FK обнуляется (SET_NULL) — сама
                запись воды не теряется, просто на время теряет привязку,
                пока update_log не пересопоставит её заново по имени.

    notes — свободная заметка пользователя к записи. Независима от food_log —
            можно иметь заметку без привязки к еде и наоборот.

    Отображаемое имя записи (когда она привязана к еде) не хранится тут
    отдельным полем-снэпшотом — берётся напрямую из FoodItem/FoodLog при
    сериализации (см. api/water.py), чтобы не расходиться с реальным
    названием блюда при его переименовании.

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
    food_item = fields.ForeignKeyField(
        "models.FoodItem",
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
