"""
Анализ фото, текстовых описаний и голосовых записей еды и напитков → КБЖУ +
клетчатка + сахар + объём воды через Gemini.

notes — необязательное уточнение к фото. Промпт формулирует его как источник
ВТОРОГО порядка: фото остаётся основным источником истины о том, ЧТО на
тарелке; notes лишь уточняет уже увиденное или (если ссылается на прошлый
приём пищи) подтягивает точные значения из истории логов.

analyze_food_text / analyze_food_voice / analyze_food_photo — все три при
наличии user_id подмешивают недавнюю историю логов (food_history.py), чтобы
ИИ понимал ссылки вида "как вчера".

language — язык ответа. Явно передаётся с фронта при каждом запросе (текущий
i18n.language), а не берётся молча из БД — так исключается риск устаревшего
User.language_code.
"""

from typing import Optional

from ai.gemini import analyze_image, analyze_audio, send_text
from ai.services.food_history import build_recent_food_history

# Маппинг language_code → человекочитаемое название для промпта.
# "uk" — стандартный ISO-код, "ua" — internal-код, которым фронт этого
# проекта называет папку локали Ukrainian (см. src/locales/ua). Оба должны
# указывать на один и тот же язык, иначе промпт получает "Ua" вместо
# "Ukrainian" и модель может съехать на случайный язык ответа.
_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ua": "Ukrainian",
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

===== SOURCE OF TRUTH HIERARCHY (read this first, it overrides everything below) =====
1. THE PHOTO is your only source of truth about what food/drinks exist and how much
   of them there is. You identify items by what you can actually SEE — shapes, colors,
   textures, containers, reference objects for scale.
2. The user's optional text note is a SECONDARY, UNVERIFIED hint. It may help you
   read a label, understand a preparation method, or refine a quantity — but it is
   NOT evidence that something exists. Treat every claim in the note with skepticism:
   a user can type anything, including things that are wrong, exaggerated, or totally
   unrelated to the photo in front of you.
3. If the note and the photo disagree about WHAT is on the photo (e.g. note says
   "chicken cutlet" but the photo shows no identifiable food), the PHOTO WINS. Never
   invent an item just because the note mentioned it. You may use the note to help
   NAME or DESCRIBE something you can already see, never to conjure something you can't.
4. If the note only adds detail about something you already identified visually
   (ingredients, "no sugar", brand, exact weight), incorporate it normally — this is
   the one case where the note is genuinely useful.
5. If the note references a past meal (e.g. "as yesterday", "same as usual") AND a
   matching entry appears in the recent food log provided below, you may reuse that
   entry's exact portion and macros for the dish you've identified in the photo — but
   only as a refinement of the AMOUNT/values for something the photo already confirms
   is present, never as evidence for adding an item that isn't visible in the photo.

===== WHEN THE PHOTO ITSELF IS NOT USABLE =====
Before identifying any dishes, judge whether the image is actually readable:
- Mostly black, mostly white/blown out, extreme motion blur, out of focus, or the
  frame contains no plausible food/drink/table/plate content at all.
If the photo is unusable in this way, you MUST return {{"error": "no_food_detected"}}
— regardless of what the note says. A note claiming "chicken cutlet, 200g" does not
change this: you cannot verify it, so you do not report it. Do not compromise by
guessing a low-confidence item "just in case" — an unusable photo always means the
error response, never a guessed dish.

===== NORMAL ANALYSIS =====
When the photo IS usable, identify ONLY the dishes, ingredients AND beverages that
are ACTUALLY VISIBLE in the photo. Estimate portion sizes by comparing to reference
objects (plate, cup, fork, hand) if visible.

CRITICAL — do not hallucinate: never add an item that is not shown in the
photo, even if it would typically accompany the visible food (e.g. do not
add a cup of tea/coffee/water unless a cup or glass is actually visible), and
even if the user's note mentions it. If you are uncertain whether something is
present, leave it out rather than guessing it into existence.

For EVERY item (food or drink) also estimate water_ml — the water-equivalent
hydration it contributes, in millilitres. Use these typical water fractions
for common drinks unless the photo or note suggests otherwise:
  water/tea/black coffee ~98%, milk ~87%, juice ~88%, soda ~89%,
  soup/broth ~92%, beer/wine ~90-95%.
Dry solid foods (bread, meat, rice, etc.) → water_ml = 0.
water_ml = liquid_volume_ml * water_fraction, rounded to the nearest 10.

Return ONLY valid JSON, no markdown, no extra text:
{{
  "meal_name": "Name in {language}",
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
- meal_name is the name the user will actually see in their food log — not a category:
  - Single dish/drink → meal_name MUST equal that one dish's name, verbatim. Never generalise
    a single item into a category ("snack", "breakfast", "dessert", etc.) — e.g. a photo of
    just cookies must get meal_name = the cookies' name, not "snack".
  - Multiple dishes → meal_name is a short, concrete description of what is actually on the
    plate (you may combine the dish names, e.g. "Vermicelli, nuggets and salad"). Only use a
    natural set-meal name (e.g. a specific fast-food combo name) if the dishes truly form one
    recognisable, branded combo — never invent generic meal-time labels like "Lunch set",
    "Breakfast combo", "Комплексный обед" etc. You cannot know the time of day or the user's
    intent from a photo alone, so never guess it.
- Order dishes logically: soups/starters → main courses → sides → salads → desserts → drinks.
- confidence reflects how certain YOU are from the visual evidence alone — a note cannot
  inflate it (except when reusing an exact history match, see rule 5 above). If confidence
  < 0.6 for any dish, set ask_user=true and explain in portion_note.
- portion_note must be phrased as YOUR observation or assumption, never as a question
  directed at the user — the app has no way for them to respond to it. Write e.g.
  "Assumed 2 eggs (typical serving)", not "How many eggs were used?".
- Always use grams for portions (liquids: use the ml-equivalent in grams), float for macros
- fiber_g = dietary fiber estimate; sugar_g = total sugars (including natural)
- total.water_ml MUST equal the sum of all dishes' water_ml
- If the photo has no food or drink, or is unusable per the rule above, return
  {{"error": "no_food_detected"}}
- Never refuse to attempt estimation for complex or mixed dishes that ARE visible — but only
  for what is actually visible in the photo, and only when the photo itself is usable.
"""

TEXT_FOOD_PROMPT_TEMPLATE = """
You are a precise nutrition analyst for a calorie and hydration tracking app.

The user describes, in free text, what they ate or drank — there is no photo.
Estimate the dishes, portions and macros from the description alone, using
typical serving sizes and standard nutritional values for the named foods.

Rules:
- Identify every distinct dish/drink mentioned. Do not invent items that
  weren't described, even implied ones (don't add a drink just because a
  meal "usually" comes with one).
- If the description is too vague to identify any food at all (e.g. empty,
  gibberish, or clearly not about food), return {{"error": "no_food_detected"}}.
- Estimate portion_g using the description's own quantities if given
  ("200g", "a bowl", "2 slices"); otherwise assume a typical serving size.
- For EVERY item estimate water_ml the same way as for a photo: dry solid
  foods → 0, drinks/soups use typical water fractions (water/tea/coffee ~98%,
  milk ~87%, juice ~88%, soda ~89%, soup ~92%, beer/wine ~90-95%).
- Because there is no photo to verify against, confidence should generally be
  lower than photo-based analysis — cap it at 0.75 (unless reusing an exact
  history match, see the history note below), and set ask_user=true with a
  clarifying portion_note whenever the description leaves real ambiguity
  about quantity or ingredients.
- portion_note must be phrased as YOUR observation or assumption, never as a
  question directed at the user — the app has no way for them to respond to
  it. Write e.g. "Assumed a medium portion (~250g)", not "How much did you eat?".

Return ONLY valid JSON, no markdown, no extra text — same shape as photo analysis:
{{
  "meal_name": "Name in {language}",
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
      "confidence": 0.7
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
  "portion_note": "Estimated from description, no photo to verify against",
  "ask_user": false
}}

Same meal_name rules as usual: for a single dish/drink, meal_name MUST equal
that dish's name verbatim — never a category like "breakfast" or "snack".
For multiple dishes, meal_name is a short concrete description of what was
described (you may combine dish names). Return ALL text in {language}.
"""

VOICE_FOOD_PROMPT_TEMPLATE = """
You are a precise nutrition analyst for a calorie and hydration tracking app.

You receive a short voice recording where the user describes, out loud, what
they ate or drank. First understand what was said (it may be in any spoken
language), then estimate the dishes, portions and macros — exactly as you
would from a text description.

Rules:
- Identify every distinct dish/drink actually mentioned in the recording. Do
  not invent items that weren't said, even implied ones.
- If the recording is silent, unintelligible, or clearly not about food,
  return {{"error": "no_food_detected"}}.
- Estimate portion_g using quantities mentioned in speech if given; otherwise
  assume a typical serving size.
- For EVERY item estimate water_ml the same way as for text/photo: dry solid
  foods → 0, drinks/soups use typical water fractions (water/tea/coffee ~98%,
  milk ~87%, juice ~88%, soda ~89%, soup ~92%, beer/wine ~90-95%).
- Because there is no photo and speech can be mis-heard, confidence should be
  conservative — cap it at 0.75 (unless reusing an exact history match, see
  the history note below), and set ask_user=true with a clarifying
  portion_note whenever real ambiguity remains.
- portion_note must be phrased as YOUR observation or assumption, never as a
  question directed at the user — the app has no way for them to respond to it.

Return ONLY valid JSON, no markdown, no extra text — same shape as photo/text analysis:
{{
  "meal_name": "Name in {language}",
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
      "confidence": 0.7
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
  "portion_note": "Estimated from voice description",
  "ask_user": false
}}

Same meal_name rules as usual: for a single dish/drink, meal_name MUST equal
that dish's name verbatim — never a category like "breakfast" or "snack".
For multiple dishes, meal_name is a short concrete description of what was
described (you may combine dish names). Return ALL text in {language},
regardless of which language the user spoke in the recording.
"""


def _build_prompt(language_code: str) -> str:
    lang = _LANG_NAMES.get(language_code, language_code.capitalize())
    return FOOD_PROMPT_TEMPLATE.format(language=lang)


def _build_text_prompt(language_code: str) -> str:
    lang = _LANG_NAMES.get(language_code, language_code.capitalize())
    return TEXT_FOOD_PROMPT_TEMPLATE.format(language=lang)


def _build_voice_prompt(language_code: str) -> str:
    lang = _LANG_NAMES.get(language_code, language_code.capitalize())
    return VOICE_FOOD_PROMPT_TEMPLATE.format(language=lang)


async def analyze_food_photo(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    notes: Optional[str] = None,
    language: str = "en",
    user_id: Optional[int] = None,
) -> dict:
    """
    Принимает сырые байты фото (+ опциональное уточнение пользователя),
    возвращает dict с meal_name, dishes[] и total{} (включая water_ml).
    Если передан user_id — подмешивает недавнюю историю логов, чтобы notes
    вида "как вчера" могли подтянуть точные значения (см. правило 5 в промпте).
    """
    prompt = _build_prompt(language)
    if user_id is not None:
        prompt += await build_recent_food_history(user_id)
    return await analyze_image(prompt, image_bytes, mime_type, user_note=notes)


async def analyze_food_text(
    description: str,
    language: str = "en",
    user_id: Optional[int] = None,
) -> dict:
    """
    Тот же контракт, что и analyze_food_photo, но источник — текстовое
    описание пользователя, без фото.
    """
    prompt = _build_text_prompt(language)
    if user_id is not None:
        prompt += await build_recent_food_history(user_id)
    return await send_text(prompt, description)


async def analyze_food_voice(
    audio_bytes: bytes,
    mime_type: str = "audio/wav",
    language: str = "en",
    user_id: Optional[int] = None,
) -> dict:
    """Тот же контракт, но источник — голосовая запись."""
    prompt = _build_voice_prompt(language)
    if user_id is not None:
        prompt += await build_recent_food_history(user_id)
    return await analyze_audio(prompt, audio_bytes, mime_type)
