from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class WaterLog(Model):
    user = fields.ForeignKeyField(
        "models.User", related_name="water_logs", on_delete=fields.CASCADE
    )
    log_date = fields.DateField()
    logged_at = fields.DatetimeField(auto_now_add=True)
    amount_ml = fields.SmallIntField()

    class Meta:
        table = "water_logs"
        indexes = [("user_id", "log_date")]
        ordering = ["-logged_at"]


WaterLogSchema = pydantic_model_creator(WaterLog, name="WaterLog")
