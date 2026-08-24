from tortoise import fields
from tortoise.models import Model


class Friendship(Model):
    """
    Связь между двумя пользователями.

    Строка создаётся ОДИН РАЗ инициатором запроса (user -> friend), не
    дублируется в обе стороны. Если B отправляет запрос A, пока у A уже
    есть pending-запрос к B — второй запрос не создаётся, а исходный
    сразу становится accepted (мгновенный "взаимный мэтч", см. api/friends.py).

    status:
      'pending'  — запрос отправлен, friend ещё не ответил
      'accepted' — дружба подтверждена
    """

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"

    user = fields.ForeignKeyField(
        "models.User", related_name="friendships_sent", on_delete=fields.CASCADE
    )
    friend = fields.ForeignKeyField(
        "models.User", related_name="friendships_received", on_delete=fields.CASCADE
    )
    status = fields.CharField(max_length=10, default=STATUS_PENDING)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "friendships"
        unique_together = [("user_id", "friend_id")]
