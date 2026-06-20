"""
Базовый клиент Gemini 2.5 Flash.

Стратегия retry: 503 UNAVAILABLE — транзиентная ошибка перегрузки модели.
Делаем до MAX_RETRIES попыток с экспоненциальной задержкой + jitter,
чтобы не создавать thundering herd при массовых запросах.
"""

import asyncio
import json
import logging
import random

from google import genai
from google.genai import types
from config import config

from typing import Optional

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=config.GEMINI_API_KEY.get_secret_value())
MODEL = "gemini-2.5-flash"

GEMINI_TIMEOUT = 30
MAX_RETRIES = 3
# Базовые задержки: 1s, 2s, 4s — удваиваются при каждой попытке
_RETRY_BASE_DELAY = 1.0


# ─── Custom exceptions ────────────────────────────────────────────────────────


class GeminiError(Exception):
    """Базовый класс для ошибок Gemini."""


class GeminiUnavailableError(GeminiError):
    """
    Gemini вернул 503 UNAVAILABLE — временная перегрузка.
    Клиентский код должен сообщить пользователю попробовать позже.
    """


# ─── Retry logic ──────────────────────────────────────────────────────────────


def _is_unavailable(exc: Exception) -> bool:
    """Определяет, является ли ошибка транзиентной перегрузкой Gemini."""
    msg = str(exc).upper()
    return "503" in msg or "UNAVAILABLE" in msg or "HIGH DEMAND" in msg


async def _with_retry(coro_factory, *, operation: str):
    """
    Выполняет coroutine с экспоненциальным backoff при 503.

    coro_factory — callable без аргументов, возвращает новый coroutine
    при каждом вызове (coroutine нельзя повторно await-ить).
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=GEMINI_TIMEOUT)
        except asyncio.TimeoutError:
            raise GeminiError(f"Gemini timeout after {GEMINI_TIMEOUT}s")
        except Exception as exc:
            if not _is_unavailable(exc):
                raise  # не 503 — пробрасываем сразу

            last_exc = exc
            if attempt == MAX_RETRIES:
                break

            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "Gemini %s unavailable (attempt %d/%d), retrying in %.1fs: %s",
                operation, attempt, MAX_RETRIES, delay, exc,
            )
            await asyncio.sleep(delay)

    logger.error("Gemini %s failed after %d attempts: %s", operation, MAX_RETRIES, last_exc)
    raise GeminiUnavailableError(
        "Gemini is temporarily unavailable due to high demand. Please try again later."
    ) from last_exc


# ─── JSON parsing ─────────────────────────────────────────────────────────────


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


# ─── Public API ───────────────────────────────────────────────────────────────


async def send_text(system_prompt: str, user_message: str) -> dict:
    def _make_coro():
        return _client.aio.models.generate_content(
            model=MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                max_output_tokens=2048,
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
        # Appended, not prepended — the model sees the fixed task first,
        # then the user's note, which is more robust if the note itself
        # reads like an instruction ("ignore calories" etc.).
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
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )

    response = await _with_retry(_make_coro, operation="analyze_image")
    return _parse_json(response.text)
