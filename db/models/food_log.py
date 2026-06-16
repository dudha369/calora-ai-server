from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class FoodLog(Model):
    """
    Одна запись еды пользователя (без деления на завтрак/обед/ужин).

    log_date  — дата питания (DATE) в локальном времени пользователя.
                Передаётся клиентом. Используется для запросов "вся еда за день".
    logged_at — UTC-момент создания записи (auto). Для сортировки внутри дня.

    Два поля нужны: пользователь в 23:58 хочет запись в "сегодня",
    а не "завтра" по UTC — это решает log_date с клиента.

    photo_url — URL фото в Cloudflare R2 / Backblaze B2 (бесплатные S3).
                NULL если добавлено вручную без фото.

    total_* пересчитываются в api/food.py после каждого изменения FoodItem.
    total_fiber_g / total_sugar_g — суммы по всем FoodItem.
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="food_logs", on_delete=fields.CASCADE
    )

    log_date = fields.DateField()
    logged_at = fields.DatetimeField(auto_now_add=True)
    photo_url = fields.TextField(null=True)

    total_calories = fields.SmallIntField(default=0)
    total_protein_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_fat_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_carbs_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_fiber_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)
    total_sugar_g = fields.DecimalField(max_digits=6, decimal_places=1, default=0)

    class Meta:
        table = "food_logs"
        indexes = [("user_id", "log_date")]
        ordering = ["-logged_at"]


FoodLogSchema = pydantic_model_creator(FoodLog, name="FoodLog")
