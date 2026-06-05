from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class AiTip(Model):
    """
    Ежедневный совет от Gemini (промт tips). Один совет в день на пользователя.
    based_on_date — дата питания, по которой сгенерирован совет.

    tip_type: 'macro_balance' | 'hydration' | 'overeating' |
              'undereating' | 'streak_praise' | 'food_quality'
    """

    user = fields.ForeignKeyField(
        "models.User", related_name="ai_tips", on_delete=fields.CASCADE
    )

    tip_text = fields.TextField()
    tip_type = fields.CharField(max_length=20)
    icon = fields.CharField(max_length=8)
    based_on_date = fields.DateField()

    class Meta:
        table = "ai_tips"
        unique_together = [("user_id", "based_on_date")]
        ordering = ["-based_on_date"]


AiTipSchema = pydantic_model_creator(AiTip, name="AiTip")
