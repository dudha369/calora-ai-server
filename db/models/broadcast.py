from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class Broadcast(Model):
    """
    История рассылок, отправленных через админ-панель.
    Статусы: pending → sending → done / failed
    """

    id = fields.IntField(pk=True)

    text = fields.TextField()
    photo_url = fields.TextField(null=True)
    segment = fields.CharField(max_length=32, default="all")
    button_text = fields.CharField(max_length=64, null=True)
    button_url = fields.TextField(null=True)

    status = fields.CharField(max_length=16, default="pending")
    total = fields.IntField(default=0)
    sent = fields.IntField(default=0)
    failed = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "broadcasts"
        ordering = ["-created_at"]


BroadcastSchema = pydantic_model_creator(Broadcast, name="Broadcast")
