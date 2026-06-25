# ai/gemini.py (полный файл после правки)

import asyncio
import json
import logging
import random
from typing import Optional

from google import genai
from google.genai import types

from config import config

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=config.GEMINI_API_KEY.get_secret_value())
MODEL = "gemini-2.5-flash"

GEMINI_TIMEOUT = 60          # было 30 — image-анализ может занимать дольше
MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Лимиты вынесены в константы: один файл для тюнинга, ноль дублирования.
# Gemini 2.5 Flash тратит thinking-токены из того же пула max_output_tokens,
# поэтому реального «места» для JSON всегда меньше, чем написано в цифре.
MAX_OUTPUT_TOKENS_TEXT  = 4_096   # советы / квесты / цели — компактный JSON
MAX_OUTPUT_TOKENS_IMAGE = 16_384  # N блюд + total + notes — нужен запас


class GeminiError(Exception):
    """Базовый класс для ошибок Gemini."""


class GeminiUnavailableError(GeminiError):
    """503 UNAVAILABLE — временная перегрузка модели."""


def _is_unavailable(exc: Exception) -> bool:
    msg = str(exc).upper()
    return "503" in msg or "UNAVAILABLE" in msg or "HIGH DEMAND" in msg


async def _with_retry(coro_factory, *, operation: str):
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=GEMINI_TIMEOUT)
        except asyncio.TimeoutError:
            raise GeminiError(f"Gemini timeout after {GEMINI_TIMEOUT}s")
        except Exception as exc:
            if not _is_unavailable(exc):
                raise

            last_exc = exc
            if attempt == MAX_RETRIES:
                break

            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "Gemini %s unavailable (attempt %d/%d), retrying in %.1fs: %s",
                operation, attempt, MAX_RETRIES, delay, exc,
            )
            await asyncio.sleep(delay)

    logger.error(
        "Gemini %s failed after %d attempts: %s", operation, MAX_RETRIES, last_exc
    )
    raise GeminiUnavailableError(
        "Gemini is temporarily unavailable due to high demand. Please try again later."
    ) from last_exc


def _parse_json(text: str) -> dict:
    text = text.strip()

    if "<think>" in text:
        end = text.find("</think>")
        text = text[end + 8:].strip() if end != -1 else text

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if text.startswith("{") and not text.endswith("}"):
            raise GeminiError(
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

    raise GeminiError(f"Cannot parse JSON from Gemini response: {text[:300]}")


async def send_text(system_prompt: str, user_message: str) -> dict:
    def _make_coro():
        return _client.aio.models.generate_content(
            model=MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                max_output_tokens=MAX_OUTPUT_TOKENS_TEXT,
                response_mime_type="application/json",
            ),
        )

    response = await _with_retry(_make_coro, operation="send_text")
    return _parse_json(response.text)


async def analyze_image(
    system_prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    user_note: Optional[str] = None,
) -> dict:
    instruction = "Analyze the food in this image."
    if user_note:
        instruction += f" User clarification: {user_note.strip()}"

    def _make_coro():
        return _client.aio.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                instruction,
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=MAX_OUTPUT_TOKENS_IMAGE,
                response_mime_type="application/json",
            ),
        )

    response = await _with_retry(_make_coro, operation="analyze_image")
    return _parse_json(response.text)
