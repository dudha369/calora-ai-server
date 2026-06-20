"""
Анализ фото еды и напитков → КБЖУ + клетчатка + сахар + объём воды через Gemini.

Каждое блюдо (включая напитки) получает поле water_ml — оценку гидратации.
Для твёрдой еды это обычно 0, для напитков/супов — оценка по типичной доле
воды (согласовано с ручными пресетами в src/pages/WaterPage.tsx, чтобы цифры
не расходились между ИИ-распознаванием и ручным вводом).

notes — необязательное уточнение, которое пользователь вводит после съёмки
фото, до запуска анализа (см. FoodNotesSheet на фронте).
"""

from ai.gemini import analyze_image

from typing import Optional

FOOD_PROMPT = """
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
{
  "dishes": [
    {
      "name": "Dish or drink name in Russian",
      "portion_g": 200,
      "calories": 350,
      "protein_g": 25.0,
      "fat_g": 12.0,
      "carbs_g": 30.0,
      "fiber_g": 4.0,
      "sugar_g": 5.0,
      "water_ml": 0,
      "confidence": 0.85
    }
  ],
  "total": {
    "calories": 350,
    "protein_g": 25.0,
    "fat_g": 12.0,
    "carbs_g": 30.0,
    "fiber_g": 4.0,
    "sugar_g": 5.0,
    "water_ml": 0
  },
  "portion_note": "Estimated based on standard plate size",
  "ask_user": false
}

Rules:
- If confidence < 0.6 for any dish, set ask_user=true and explain in portion_note
- Always use grams for portions (liquids: use the ml-equivalent in grams), float for macros
- fiber_g = dietary fiber estimate; sugar_g = total sugars (including natural)
- total.water_ml MUST equal the sum of all dishes' water_ml
- If the photo has no food or drink, return {"error": "no_food_detected"}
- Never refuse. Always attempt estimation even for complex or mixed dishes.
"""


async def analyze_food_photo(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    notes: Optional[str] = None,
) -> dict:
    """
    Принимает сырые байты фото (+ опциональное уточнение пользователя),
    возвращает dict с dishes[] и total{} (включая water_ml на обоих уровнях).
    """
    return await analyze_image(FOOD_PROMPT, image_bytes, mime_type, user_note=notes)
