"""
Базовый клиент Gemini 2.5 Flash.
"""

import asyncio
import json

from google import genai
from google.genai import types
from config import config

_client = genai.Client(api_key=config.GEMINI_API_KEY.get_secret_value())
MODEL = "gemini-2.5-flash"

# Таймаут на ответ от Gemini (секунды).
# Если API зависнет — запрос упадёт с TimeoutError вместо бесконечного ожидания.
GEMINI_TIMEOUT = 30


def _parse_json(text: str) -> dict:
    text = text.strip()

    if "<think>" in text:
        end = text.find("</think>")
        text = text[end + 8:].strip() if end != -1 else text

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Явная диагностика: если JSON начинается с { но не закрыт —
        # значит ответ обрезан из-за max_output_tokens.
        if text.startswith("{") and not text.endswith("}"):
            raise ValueError(
                f"Gemini response truncated (max_output_tokens too low). "
                f"Preview: {text[:300]}"
            ) from e

    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from Gemini response: {text[:300]}")


async def send_text(system_prompt: str, user_message: str) -> dict:
    response = await asyncio.wait_for(
        _client.aio.models.generate_content(
            model=MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        ),
        timeout=GEMINI_TIMEOUT,
    )
    return _parse_json(response.text)


async def analyze_image(
    system_prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg"
) -> dict:
    response = await asyncio.wait_for(
        _client.aio.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                "Analyze the food in this image.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        ),
        timeout=GEMINI_TIMEOUT,
    )
    return _parse_json(response.text)
