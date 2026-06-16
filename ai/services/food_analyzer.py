"""
Анализ фото еды → КБЖУ + клетчатка + сахар через Gemini.
"""

from ai.gemini import analyze_image

FOOD_PROMPT = """
You are a precise nutrition analyst. The user sends a food photo.
Identify ALL dishes and ingredients visible. Estimate portion sizes
by comparing to reference objects (plate, fork, hand) if visible.

Return ONLY valid JSON, no markdown, no extra text:
{
  "dishes": [
    {
      "name": "Dish name in Russian",
      "portion_g": 200,
      "calories": 350,
      "protein_g": 25.0,
      "fat_g": 12.0,
      "carbs_g": 30.0,
      "fiber_g": 4.0,
      "sugar_g": 5.0,
      "confidence": 0.85
    }
  ],
  "total": {
    "calories": 350,
    "protein_g": 25.0,
    "fat_g": 12.0,
    "carbs_g": 30.0,
    "fiber_g": 4.0,
    "sugar_g": 5.0
  },
  "portion_note": "Estimated based on standard plate size",
  "ask_user": false
}

Rules:
- If confidence < 0.6 for any dish, set ask_user=true and explain in portion_note
- Always use grams for portions, float for macros
- fiber_g = dietary fiber estimate; sugar_g = total sugars (including natural)
- If photo has no food, return {"error": "no_food_detected"}
- Never refuse. Always attempt estimation even for complex dishes.
"""


async def analyze_food_photo(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Принимает сырые байты фото, возвращает dict с dishes[] и total{}.
    """
    return await analyze_image(FOOD_PROMPT, image_bytes, mime_type)
