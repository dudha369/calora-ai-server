from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class User(Model):
    """
    Пользователь Telegram.
    telegram_id — реальный TG ID, не auto-increment (generated=False отключает SERIAL).
    Стрик считается по выполнению дневной КБЖУ-цели, не по открытию приложения.
    Обновляется в ai/services/daily_close.py при проверке итогов дня.
    """

    telegram_id = fields.BigIntField(pk=True, generated=False)
    full_name = fields.CharField(max_length=120)
    username = fields.CharField(max_length=64, null=True)
    language_code = fields.CharField(max_length=8, default="ru")

    current_streak = fields.IntField(default=0)
    max_streak = fields.IntField(default=0)
    quests_completed = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "users"


UserSchema = pydantic_model_creator(User, name="User")
