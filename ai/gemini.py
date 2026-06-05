"""
Базовый клиент для Gemini 2.5 Flash через официальный SDK google-genai.
Все AI-сервисы импортируют send_text() и analyze_image() отсюда.
"""

import json
from google import genai
from google.genai import types
from config_reader import config

_client = genai.Client(api_key=config.GEMINI_API_KEY.get_secret_value())

MODEL = "gemini-2.5-flash"


def _parse_json(text: str) -> dict:
    """Парсит JSON из ответа, убирает возможные markdown-обёртки."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


async def send_text(system_prompt: str, user_message: str) -> dict:
    """
    Текстовый запрос к Gemini.
    Используется для: расчёта целей, советов, квестов.
    Возвращает распарсенный JSON.
    """
    response = await _client.aio.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.4,
            max_output_tokens=1000,
        ),
    )
    return _parse_json(response.text)


async def analyze_image(
    system_prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg"
) -> dict:
    """
    Мультимодальный запрос (фото + текст) к Gemini.
    Используется только для анализа еды по фото.
    image_bytes — сырые байты файла (не base64).
    Возвращает распарсенный JSON.
    """
    response = await _client.aio.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            "Analyze the food in this image.",
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            max_output_tokens=1000,
        ),
    )
    return _parse_json(response.text)
