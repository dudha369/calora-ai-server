"""
Расчёт дневных целей: формула на сервере + персонализация через Gemini.
"""

import logging
from datetime import date

from ai.gemini import send_text

logger = logging.getLogger(__name__)

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "extreme": 1.9,
}

GOALS_PROMPT = """
You are a nutrition coach. You receive a user profile with pre-calculated
nutritional goals (via Mifflin-St Jeor formula). Your task is to ADD
personalization: adjust targets slightly based on restrictions and medical
conditions, and generate a brief motivational tip in Russian.

Return ONLY valid JSON:
{
  "adjusted_goals": {
    "calories": 1800,
    "protein_g": 140,
    "fat_g": 60,
    "carbs_g": 180,
    "water_ml": 2400
  },
  "tip_of_day": "Мотивационная фраза на русском (1-2 предложения)"
}

Important: adjust calories no more than ±150 from base. Keep it realistic.
"""


def calculate_age(birth_date: date, today: date | None = None) -> int:
    """
    Вычисляет полный возраст в годах на указанную дату.
    Учитывает, был ли уже день рождения в текущем году.
    """
    if today is None:
        today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def calculate_base_goals(profile_data: dict) -> dict:
    """
    Считает базовые нормы по формуле Миффлина-Сент-Жеора.
    profile_data: {gender, birth_date|age, height_cm, weight_kg, goal_type, activity_level}

    Поддерживает оба варианта:
    - birth_date (date) — вычисляет возраст динамически
    - age (int) — для обратной совместимости и тестов
    """
    w = float(profile_data["weight_kg"])
    h = float(profile_data["height_cm"])

    if "birth_date" in profile_data and profile_data["birth_date"] is not None:
        bd = profile_data["birth_date"]
        if isinstance(bd, str):
            bd = date.fromisoformat(bd)
        a = calculate_age(bd)
    else:
        a = int(profile_data["age"])

    gender_bonus = 5 if profile_data["gender"] == "male" else -161

    bmr = 10 * w + 6.25 * h - 5 * a + gender_bonus
    tdee = bmr * ACTIVITY_MULTIPLIERS.get(profile_data["activity_level"], 1.55)

    goal = profile_data.get("goal_type", "maintain")
    if goal == "lose":
        calories = tdee - 500
    elif goal == "gain":
        calories = tdee + 300
    else:
        calories = tdee

    calories = max(1200, round(calories))
    protein_g = round(w * 1.8, 1)
    fat_g = round(calories * 0.30 / 9, 1)
    carbs_g = round((calories - protein_g * 4 - fat_g * 9) / 4, 1)
    water_ml = max(1500, int(w * 33))

    return {
        "calories": calories,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
        "water_ml": water_ml,
    }


async def calculate_and_personalize(profile_data: dict) -> dict:
    """
    1. Считает базовые нормы формулой
    2. Отправляет в Gemini для персонализации
    Возвращает: {"calories", "protein_g", "fat_g", "carbs_g", "water_ml", "ai_tip"}
    """
    base = calculate_base_goals(profile_data)

    user_msg = str({**profile_data, **{"base_goals": base}})
    try:
        result = await send_text(GOALS_PROMPT, user_msg)
        goals = result.get("adjusted_goals", base)
        ai_tip = result.get("tip_of_day")
    except Exception as e:
        logger.warning("Gemini personalization failed, using base goals: %s", e)
        # Если Gemini недоступен — используем базовые цели без персонализации
        goals = base
        ai_tip = None

    return {**goals, "ai_tip": ai_tip}
