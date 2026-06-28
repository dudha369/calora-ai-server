from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class User(Model):
    """
    Пользователь Telegram.
    telegram_id — реальный TG ID, не auto-increment (generated=False отключает SERIAL).
    Стрик считается по выполнению дневной КБЖУ-цели, не по открытию приложения.
    Обновляется в ai/services/daily_close.py при проверке итогов дня.

    last_active_at — обновляется при каждом API-запросе (get_current_user).
    is_active / deleted_at — для soft delete (GDPR, восстановление аккаунтов).
    """

    telegram_id = fields.BigIntField(pk=True, generated=False)
    full_name = fields.CharField(max_length=120)
    username = fields.CharField(max_length=64, null=True)
    language_code = fields.CharField(max_length=8, default="ru")

    current_streak = fields.IntField(default=0)
    max_streak = fields.IntField(default=0)
    streak_restores_available = fields.SmallIntField(default=3)
    streak_restores_reset_at = fields.DateField(null=True)
    streak_before_break = fields.IntField(null=True)

    quests_completed = fields.IntField(default=0)
    last_streak_check_date = fields.DateField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    last_active_at = fields.DatetimeField(null=True)

    is_active = fields.BooleanField(default=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "users"


UserSchema = pydantic_model_creator(User, name="User")
