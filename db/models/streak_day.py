from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class StreakDay(Model):
    """
    Построчная история дней для расчёта серии — нужна StreakPopup, чтобы
    показать какие дни продлили серию обычным выполнением цели, какие были
    прощены щитом восстановления, а какие сорвали серию.

    status:
      'met'      — цель дня выполнена, серия продлена обычным путём
      'missed'   — цель дня не выполнена, серия сброшена в этот день
      'restored' — день прощён щитом (restore_streak), был 'missed'

    Запись для "сегодня" создаётся только когда день уже засчитан
    (sync_today_credit_state) — пока день не закончился и цель не достигнута,
    записи нет вообще (фронт сам показывает "в процессе").
    """

    STATUS_MET = "met"
    STATUS_MISSED = "missed"
    STATUS_RESTORED = "restored"

    user = fields.ForeignKeyField(
        "models.User", related_name="streak_days", on_delete=fields.CASCADE
    )
    log_date = fields.DateField()
    status = fields.CharField(max_length=10)

    class Meta:
        table = "streak_days"
        unique_together = [("user_id", "log_date")]
        ordering = ["-log_date"]


StreakDaySchema = pydantic_model_creator(StreakDay, name="StreakDay")