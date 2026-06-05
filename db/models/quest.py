from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class Quest(Model):
    """
    Квест пользователя. Генерируется Gemini раз в неделю.

    Жизненный цикл:
      active → done   (current_value >= target_value) → User.quests_completed += 1
      active → failed (expires_at истёк)

    quest_key — логика прогресса на бэкенде:
      'protein_goal'  → +1 за день где protein >= DailyGoal.protein_g
      'streak'        → = User.current_streak
      'photo_log'     → +1 за FoodLog с photo_url != null
      'hydration'     → +1 за день где вода >= DailyGoal.water_ml
      'calorie_goal'  → +1 за день попадания в ±10% от DailyGoal.calories
    """

    STATUS_ACTIVE = "active"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    user = fields.ForeignKeyField(
        "models.User", related_name="quests", on_delete=fields.CASCADE
    )

    quest_key = fields.CharField(max_length=40)
    title = fields.CharField(max_length=100)
    description = fields.TextField()
    icon = fields.CharField(max_length=8)

    target_value = fields.DecimalField(max_digits=8, decimal_places=1)
    current_value = fields.DecimalField(max_digits=8, decimal_places=1, default=0)

    status = fields.CharField(max_length=10, default=STATUS_ACTIVE)
    expires_at = fields.DatetimeField()
    completed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "quests"
        indexes = [("user_id", "status")]
        ordering = ["-expires_at"]


QuestSchema = pydantic_model_creator(Quest, name="Quest")
