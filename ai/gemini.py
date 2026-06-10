"""
Базовый клиент Gemini 2.5 Flash.
response_mime_type="application/json" — гарантирует чистый JSON без think-тегов
и markdown-обёрток. Самый надёжный способ работать с thinking-моделями.
"""

import json
from google import genai
from google.genai import types
from config import config

_client = genai.Client(api_key=config.GEMINI_API_KEY.get_secret_value())
MODEL = "gemini-2.5-flash"


def _parse_json(text: str) -> dict:
    """
    Парсит JSON из ответа. Порядок попыток:
    1. Прямой парсинг (при response_mime_type=json всегда чистый JSON)
    2. Убирает markdown ```json``` обёртку
    3. Ищет первый { ... } блок (если модель добавила пояснительный текст)
    """
    text = text.strip()

    if "<think>" in text:
        end = text.find("</think>")
        text = text[end + 8:].strip() if end != -1 else text

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])

    raise ValueError(f"Cannot parse JSON from Gemini response: {text[:200]}")


async def send_text(system_prompt: str, user_message: str) -> dict:
    response = await _client.aio.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.4,
            max_output_tokens=1000,
            response_mime_type="application/json",
        ),
    )
    return _parse_json(response.text)


async def analyze_image(
    system_prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg"
) -> dict:
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
            response_mime_type="application/json",
        ),
    )
    return _parse_json(response.text)
