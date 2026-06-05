from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class UserProfile(Model):
    """
    Биометрия и настройки пользователя (1:1 с User).
    Создаётся при завершении онбординга (POST /api/onboarding/complete).
    При изменении любого поля API-хендлер вызывает пересчёт DailyGoal.

    gender:         'male' | 'female'
    goal_type:      'lose' | 'maintain' | 'gain'
    activity_level: 'sedentary' | 'light' | 'moderate' | 'active' | 'extreme'
    water_track:    'auto' | 'manual' | 'none'
    dietary_restrictions: ['Вегетарианство', 'Без глютена', ...]
    medical_conditions:   ['Сахарный диабет 2 типа', ...]
    """

    user = fields.OneToOneField(
        "models.User", related_name="profile", on_delete=fields.CASCADE
    )

    gender = fields.CharField(max_length=6)
    age = fields.SmallIntField()
    height_cm = fields.SmallIntField()
    weight_kg = fields.DecimalField(max_digits=5, decimal_places=1)

    goal_type = fields.CharField(max_length=10)
    target_weight_kg = fields.DecimalField(max_digits=5, decimal_places=1, null=True)
    activity_level = fields.CharField(max_length=12)

    water_track = fields.CharField(max_length=6, default="auto")  # auto | manual | none
    water_goal_ml = fields.SmallIntField(null=True)

    dietary_restrictions = fields.JSONField(default=list)
    allergy_note = fields.TextField(null=True)
    medical_conditions = fields.JSONField(default=list)

    class Meta:
        table = "user_profiles"


UserProfileSchema = pydantic_model_creator(UserProfile, name="UserProfile", exclude=("user",))
