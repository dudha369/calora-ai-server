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

MODEL = "gemini-flash-latest"
FALLBACK_MODEL = "gemini-flash-lite-latest"

# Понижено с 60/3: раньше таймаут вообще не ретраился (см. баг), поэтому
# один неудачный запрос сразу становился 500. Теперь таймаут ретраится
# как временная перегрузка, поэтому общий бюджет времени держим в узде —
# короче таймаут на попытку, меньше попыток на модель.
GEMINI_TIMEOUT = 45
MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0

MAX_OUTPUT_TOKENS_TEXT = 4_096
MAX_OUTPUT_TOKENS_IMAGE = 16_384


class GeminiError(Exception):
    """Базовый класс для ошибок Gemini."""


class GeminiUnavailableError(GeminiError):
    """Временная перегрузка или таймаут — есть смысл ретраить/фолбэчить."""


class GeminiQuotaExceededError(GeminiError):
    """429 RESOURCE_EXHAUSTED — дневной/минутный лимит исчерпан.
    Ретраить одну и ту же модель бессмысленно — обрабатывается переключением
    на FALLBACK_MODEL в _generate_with_fallback."""


def _is_unavailable(exc: Exception) -> bool:
    msg = str(exc).upper()
    if "RESOURCE_EXHAUSTED" in msg:
        return False
    return "503" in msg or "UNAVAILABLE" in msg or "HIGH DEMAND" in msg


def _is_quota_exceeded(exc: Exception) -> bool:
    msg = str(exc).upper()
    return "RESOURCE_EXHAUSTED" in msg or "429" in msg


async def _with_retry(coro_factory, *, operation: str, max_retries: int = MAX_RETRIES):
    """
    Ретраит таймаут И 503 одинаково — оба являются временной перегрузкой
    со стороны Gemini, а не поводом сразу падать пользователю в 500.
    Quota (429/RESOURCE_EXHAUSTED) пробрасывается сразу — её обрабатывает
    _generate_with_fallback переключением модели.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=GEMINI_TIMEOUT)
        except asyncio.TimeoutError as exc:
            last_exc = exc
        except Exception as exc:
            if _is_quota_exceeded(exc):
                raise GeminiQuotaExceededError(str(exc)) from exc
            if not _is_unavailable(exc):
                raise
            last_exc = exc

        if attempt == max_retries:
            break

        delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
        logger.warning(
            "Gemini %s unavailable (attempt %d/%d), retrying in %.1fs: %s",
            operation,
            attempt,
            max_retries,
            delay,
            last_exc,
        )
        await asyncio.sleep(delay)

    logger.error(
        "Gemini %s failed after %d attempts: %s", operation, max_retries, last_exc
    )
    raise GeminiUnavailableError(
        "Gemini is temporarily unavailable due to high demand. Please try again later."
    ) from last_exc


async def _generate_with_fallback(build_coro, *, operation: str):
    """
    MODEL (flash) → при квоте ИЛИ при устойчивой перегрузке/таймауте
    переключается на FALLBACK_MODEL (flash-lite, отдельная квота, обычно
    менее нагружен). Раньше fallback срабатывал только на quota — из-за
    этого таймауты/503 сразу летели пользователю без единого шанса на
    более лёгкую модель.

    Fallback делает только одну попытку (max_retries=1) — иначе суммарное
    время ожидания для юзера улетает за пределы разумного (2 модели по
    несколько ретраев каждая = минуты ожидания одного запроса).
    """
    try:
        return await _with_retry(lambda: build_coro(MODEL), operation=operation)
    except (GeminiQuotaExceededError, GeminiUnavailableError) as exc:
        logger.warning(
            "Gemini %s: %s on %s, falling back to %s",
            operation,
            type(exc).__name__,
            MODEL,
            FALLBACK_MODEL,
        )
        return await _with_retry(
            lambda: build_coro(FALLBACK_MODEL),
            operation=f"{operation}(fallback)",
            max_retries=1,
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
