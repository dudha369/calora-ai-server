"""
Анализ фото еды и напитков → КБЖУ + клетчатка + сахар + объём воды через Gemini.

Каждое блюдо (включая напитки) получает поле water_ml — оценку гидратации.
Для твёрдой еды это обычно 0, для напитков/супов — оценка по типичной доле
воды (согласовано с ручными пресетами в src/pages/WaterPage.tsx, чтобы цифры
не расходились между ИИ-распознаванием и ручным вводом).

notes — необязательное уточнение, которое пользователь вводит после съёмки
фото, до запуска анализа (см. FoodNotesSheet на фронте).

language — язык приложения пользователя (из User.language_code). Все названия
блюд возвращаются на этом языке.
"""

from ai.gemini import analyze_image

from typing import Optional

# Маппинг language_code → человекочитаемое название для промпта.
# Fallback — English.
_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "uk": "Ukrainian",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "pt": "Portuguese",
    "it": "Italian",
    "tr": "Turkish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

FOOD_PROMPT_TEMPLATE = """
You are a precise nutrition analyst for a calorie and hydration tracking app.
The user sends a photo of food and/or drinks, optionally with a short
clarifying note (portion size, ingredients, "no sugar", etc.) — if a note is
present, trust it over your own visual guess when the two conflict.

Identify ALL dishes, ingredients AND beverages visible. Estimate portion
sizes by comparing to reference objects (plate, cup, fork, hand) if visible.

For EVERY item (food or drink) also estimate water_ml — the water-equivalent
hydration it contributes, in millilitres. Use these typical water fractions
for common drinks unless the photo or note suggests otherwise:
  water/tea/black coffee ~98%, milk ~87%, juice ~88%, soda ~89%,
  soup/broth ~92%, beer/wine ~90-95%.
Dry solid foods (bread, meat, rice, etc.) → water_ml = 0.
water_ml = liquid_volume_ml * water_fraction, rounded to the nearest 10.

Return ONLY valid JSON, no markdown, no extra text:
{{
  "meal_name": "Overall meal name in {language}",
  "dishes": [
    {{
      "name": "Dish or drink name in {language}",
      "portion_g": 200,
      "calories": 350,
      "protein_g": 25.0,
      "fat_g": 12.0,
      "carbs_g": 30.0,
      "fiber_g": 4.0,
      "sugar_g": 5.0,
      "water_ml": 0,
      "confidence": 0.85
    }}
  ],
  "total": {{
    "calories": 350,
    "protein_g": 25.0,
    "fat_g": 12.0,
    "carbs_g": 30.0,
    "fiber_g": 4.0,
    "sugar_g": 5.0,
    "water_ml": 0
  }},
  "portion_note": "Estimated based on standard plate size",
  "ask_user": false
}}

Rules:
- Return ALL text values (meal_name, dish names) in {language}. Do not add translations in parentheses.
- meal_name: a short, recognisable label for the whole meal.
  - Single dish → meal_name equals that dish's name.
  - Multiple dishes → a concise generalising name (e.g. "Lunch set", "Big Mac Meal", "Breakfast combo").
- Order dishes logically: soups/starters → main courses → sides → salads → desserts → drinks.
- If confidence < 0.6 for any dish, set ask_user=true and explain in portion_note
- Always use grams for portions (liquids: use the ml-equivalent in grams), float for macros
- fiber_g = dietary fiber estimate; sugar_g = total sugars (including natural)
- total.water_ml MUST equal the sum of all dishes' water_ml
- If the photo has no food or drink, return {{"error": "no_food_detected"}}
- Never refuse. Always attempt estimation even for complex or mixed dishes.
"""


def _build_prompt(language_code: str) -> str:
    """Подставляет язык в шаблон промпта."""
    lang = _LANG_NAMES.get(language_code, language_code.capitalize())
    return FOOD_PROMPT_TEMPLATE.format(language=lang)


async def analyze_food_photo(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    notes: Optional[str] = None,
    language: str = "en",
) -> dict:
    """
    Принимает сырые байты фото (+ опциональное уточнение пользователя),
    возвращает dict с meal_name, dishes[] и total{}
    (включая water_ml на обоих уровнях).

    language — код языка пользователя (en, ru, uk, …). Все названия блюд
    и meal_name возвращаются на этом языке.
    """
    prompt = _build_prompt(language)
    return await analyze_image(prompt, image_bytes, mime_type, user_note=notes)
