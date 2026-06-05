from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class DailyGoal(Model):
    """
    Рассчитанные дневные нормы (1:1 с User).
    Пересчитывается при изменении UserProfile через ai/services/goal_calculator.py.

    Формула Миффлина-Сент-Жеора (считается на сервере без ИИ):
        BMR = 10*вес + 6.25*рост - 5*возраст + (5 если male, -161 если female)
        multipliers: sedentary=1.2, light=1.375, moderate=1.55, active=1.725, extreme=1.9
        TDEE = BMR * multiplier
        calories = TDEE - 500 (lose) | TDEE (maintain) | TDEE + 300 (gain)
        protein_g = round(вес * 1.8, 1)
        fat_g     = round(calories * 0.30 / 9, 1)
        carbs_g   = round((calories - protein_g*4 - fat_g*9) / 4, 1)
        water_ml  = max(int(вес * 33), 1500)

    ai_tip — мотивационная фраза от Gemini (промт goals).
    Генерируется один раз при создании/обновлении профиля.
    """

    user = fields.OneToOneField(
        "models.User", related_name="daily_goal", on_delete=fields.CASCADE
    )

    calories = fields.SmallIntField()
    protein_g = fields.DecimalField(max_digits=5, decimal_places=1)
    fat_g = fields.DecimalField(max_digits=5, decimal_places=1)
    carbs_g = fields.DecimalField(max_digits=5, decimal_places=1)
    water_ml = fields.SmallIntField()
    ai_tip = fields.TextField(null=True)

    class Meta:
        table = "daily_goals"


DailyGoalSchema = pydantic_model_creator(DailyGoal, name="DailyGoal", exclude=("user",))
