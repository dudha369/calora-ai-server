from tortoise import fields
from tortoise.models import Model


class OnboardingDraft(Model):
    """
    Черновик онбординга — хранит частично заполненные данные пока пользователь
    проходит страницы. Удаляется при вызове POST /api/onboarding/complete.

    activity_level хранится как float-мультипликатор (1.2, 1.375…),
    конвертируется в строку при создании UserProfile.

    height/weight всегда хранятся в метрике (cm/kg),
    *_unit — предпочтения отображения для фронтенда.
    """

    user = fields.OneToOneField(
        "models.User", related_name="onboarding_draft", on_delete=fields.CASCADE
    )

    step = fields.SmallIntField(default=0)

    # Страница 1
    gender = fields.CharField(max_length=6, null=True)
    # Страница 2
    age = fields.SmallIntField(null=True)
    # Страница 3
    height_cm = fields.SmallIntField(null=True)
    # Страница 4
    weight_kg = fields.DecimalField(max_digits=5, decimal_places=1, null=True)
    # Страница 5
    goal = fields.CharField(max_length=10, null=True)
    # Страница 6 (только если goal != maintain)
    target_weight = fields.DecimalField(max_digits=5, decimal_places=1, null=True)
    # Страница 7
    activity_level = fields.FloatField(null=True)  # 1.2 | 1.375 | 1.55 | 1.725 | 1.9
    # Страница 8
    dietary_restrictions = fields.JSONField(default=list)
    allergy_note = fields.TextField(null=True)
    # Страница 9
    water_track = fields.CharField(max_length=6, null=True)  # auto | manual | none
    water_goal_ml = fields.SmallIntField(null=True)
    # Страница 10
    medical_conditions = fields.JSONField(default=list)

    class Meta:
        table = "onboarding_drafts"
