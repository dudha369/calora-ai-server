# ai/gemini.py

import asyncio
import json
import logging
import random
from typing import Optional

from google import genai
from google.genai import types

from config import config

logger = logging.getLogger(__name__)

_client = genai.Client(
    api_key=config.GEMINI_API_KEY.get_secret_value(),
    http_options={"base_url": config.CLOUDFLARE_WORKER_ENDPOINT.get_secret_value()},
)
MODEL = "gemini-2.5-flash"
# Более лёгкая модель с заметно выше бесплатным дневным лимитом (RPD) —
# используется как автоматический fallback, когда MODEL упирается в квоту.
FALLBACK_MODEL = "gemini-2.5-flash-lite"

GEMINI_TIMEOUT = 60
MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

MAX_OUTPUT_TOKENS_TEXT = 4_096
MAX_OUTPUT_TOKENS_IMAGE = 16_384


class GeminiError(Exception):
    """Базовый класс для ошибок Gemini."""


class GeminiUnavailableError(GeminiError):
    """503 UNAVAILABLE — временная перегрузка модели. Есть смысл ретраить."""


class GeminiQuotaExceededError(GeminiError):
    """429 RESOURCE_EXHAUSTED — дневной/минутный лимит запросов исчерпан.
    Ретраить одну и ту же модель бессмысленно — квота не снимется за
    секунды. Обрабатывается на уровне _generate_with_fallback переключением
    на FALLBACK_MODEL, а не здесь."""


def _is_unavailable(exc: Exception) -> bool:
    msg = str(exc).upper()
    if "RESOURCE_EXHAUSTED" in msg:
        return False
    return "503" in msg or "UNAVAILABLE" in msg or "HIGH DEMAND" in msg


def _is_quota_exceeded(exc: Exception) -> bool:
    msg = str(exc).upper()
    return "RESOURCE_EXHAUSTED" in msg or "429" in msg


async def _with_retry(coro_factory, *, operation: str):
    """Ретраит ТОЛЬКО временную перегрузку (503). Quota (429) пробрасывает
    сразу как GeminiQuotaExceededError — её обрабатывает вызывающий код
    (см. _generate_with_fallback)."""
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=GEMINI_TIMEOUT)
        except asyncio.TimeoutError:
            raise GeminiError(f"Gemini timeout after {GEMINI_TIMEOUT}s")
        except Exception as exc:
            if _is_quota_exceeded(exc):
                raise GeminiQuotaExceededError(str(exc)) from exc

            if not _is_unavailable(exc):
                raise

            last_exc = exc
            if attempt == MAX_RETRIES:
                break

            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "Gemini %s unavailable (attempt %d/%d), retrying in %.1fs: %s",
                operation,
                attempt,
                MAX_RETRIES,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    logger.error(
        "Gemini %s failed after %d attempts: %s", operation, MAX_RETRIES, last_exc
    )
    raise GeminiUnavailableError(
        "Gemini is temporarily unavailable due to high demand. Please try again later."
    ) from last_exc


async def _generate_with_fallback(build_coro, *, operation: str):
    """
    Пробует MODEL (flash); если он упёрся в дневную квоту — автоматически
    переключается на FALLBACK_MODEL (flash-lite), у которого выше бесплатный
    RPD. build_coro(model: str) строит один и тот же запрос под любую модель.
    Если квота исчерпана и там, и там — пробрасывает GeminiQuotaExceededError
    дальше (её ловит api/food.py и превращает в 429 "ai_quota_exceeded").
    """
    try:
        return await _with_retry(lambda: build_coro(MODEL), operation=operation)
    except GeminiQuotaExceededError:
        logger.warning(
            "Gemini %s: quota exceeded on %s, falling back to %s",
            operation,
            MODEL,
            FALLBACK_MODEL,
        )
        return await _with_retry(
            lambda: build_coro(FALLBACK_MODEL), operation=f"{operation}(fallback)"
        )


def _parse_json(text: str) -> dict:
    text = text.strip()

    if "<think>" in text:
        end = text.find("</think>")
        text = text[end + 8 :].strip() if end != -1 else text

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
    def _make_coro(model: str):
        return _client.aio.models.generate_content(
            model=model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                max_output_tokens=MAX_OUTPUT_TOKENS_TEXT,
                response_mime_type="application/json",
            ),
        )

    response = await _generate_with_fallback(_make_coro, operation="send_text")
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

    def _make_coro(model: str):
        return _client.aio.models.generate_content(
            model=model,
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

    response = await _generate_with_fallback(_make_coro, operation="analyze_image")
    return _parse_json(response.text)


async def analyze_audio(
    system_prompt: str,
    audio_bytes: bytes,
    mime_type: str = "audio/wav",
) -> dict:
    def _make_coro(model: str):
        return _client.aio.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                "Listen to this audio and follow the system instructions.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                max_output_tokens=MAX_OUTPUT_TOKENS_IMAGE,
                response_mime_type="application/json",
            ),
        )

    response = await _generate_with_fallback(_make_coro, operation="analyze_audio")
    return _parse_json(response.text)
