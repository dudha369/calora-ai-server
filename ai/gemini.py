"""
AI client via OpenRouter — US infrastructure, no geo-restrictions, free tier.

Public API unchanged:
  send_text(system_prompt, user_message) → dict
  analyze_image(system_prompt, image_bytes, mime_type, user_note) → dict

Почему OpenRouter, а не прямой Gemini API:
  • US-серверы → работает с любого IP в мире
  • Free tier покрывает MVP-нагрузку (~200 req/day на модель)
  • Multi-model fallback: 429 на одной → автоматически следующая
  • OpenAI-совместимый API → минимальный код

Ключ: https://openrouter.ai/keys (бесплатно, без карты)
"""

import asyncio
import base64
import json
import logging
import random
from typing import Optional

import httpx
from config import config

logger = logging.getLogger(__name__)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Бесплатные модели в порядке предпочтения.
# При rate-limit (429) или удалении (404) → автоматически переходим к следующей
_VISION_MODELS = [
    "google/gemini-2.5-flash-preview:free",            # Новая версия Gemini (основная)
    "meta-llama/llama-3.2-11b-vision-instruct:free",   # Надежная замена от Meta
]

_TEXT_MODELS = [
    "google/gemini-2.5-flash-preview:free",
    "meta-llama/llama-3.3-70b-instruct:free",          # Отличная текстовая модель
    "deepseek/deepseek-r1:free"                        # Альтернатива для логики
]


# ── Exceptions (сохраняем совместимость с api/food.py) ────────────────────────

class GeminiError(Exception):
    """Неустранимая ошибка AI-клиента."""


class GeminiUnavailableError(GeminiError):
    """Все модели временно недоступны — можно сообщить пользователю."""


# Внутренние сигналы управления потоком — не выходят за пределы модуля.
class _RateLimited(Exception):
    """429 — перейти к следующей модели немедленно."""


class _Retryable(Exception):
    """5xx / timeout — повторить запрос к той же модели с задержкой."""
    def __init__(self, status: int, detail: str = "") -> None:
        self.status = status
        self.detail = detail

class _SkipToNextModel(Exception):
    """Исключение для немедленного перехода к следующей модели."""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY.get_secret_value()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://calora.app",  # идентификация для OpenRouter dashboard
        "X-Title": "Calora AI",
    }


def _parse_json(text: str) -> dict:
    """
    Парсит JSON из ответа модели, обрабатывая все типичные обёртки.
    Порядок попыток от самого быстрого к самому терпимому.
    """
    text = text.strip()

    # Reasoning-модели оборачивают вывод в <think>...</think>
    if "<think>" in text:
        end = text.find("</think>")
        text = (text[end + 8:] if end != -1 else text).strip()

    # 1. Прямой парсинг (идеальный случай)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Markdown ```json ... ``` блоки
    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip().lstrip("json").strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # 3. Вырезаем первый JSON-объект из произвольного текста
    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise GeminiError(f"Cannot parse JSON from AI response: {text[:300]}")


async def _call_once(
    client: httpx.AsyncClient,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> dict:
    """
    Один HTTP-запрос к OpenRouter без retry.
    Бросает _RateLimited, _Retryable или GeminiError — никогда не возвращает None.
    """
    try:
        resp = await client.post(
            _ENDPOINT,
            headers=_headers(),
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
    except httpx.TimeoutException as exc:
        raise _Retryable(504, "timeout") from exc
    except httpx.ConnectError as exc:
        raise _Retryable(503, "connect error") from exc

    if resp.status_code == 200:
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json(content)

    if resp.status_code in (429, 404, 403):
        logger.info("OpenRouter: %s недоступна (статус %d), переключаюсь...", model, resp.status_code)
        raise _SkipToNextModel()

    if resp.status_code in (500, 502, 503, 504):
        logger.warning("OpenRouter: %s → %d: %s", model, resp.status_code, resp.text[:100])
        raise _Retryable(resp.status_code)

    raise GeminiError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")


async def _request(
    models: list[str],
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> dict:
    """
    Оркестратор: model fallback + per-model exponential backoff.

    Алгоритм:
      for model in models:
        for attempt in 1..MAX_RETRIES:
          success → return
          429     → break (next model, no delay)
          5xx     → sleep + retry same model
      → GeminiUnavailableError
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for model in models:
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    return await _call_once(
                        client, model, messages, temperature, max_tokens
                    )

                except _SkipToNextModel:
                    continue  # Продолжаем цикл, пробуем следующую модель

                except _RateLimited:
                    break  # немедленно к следующей модели, без задержки

                except _Retryable as exc:
                    if attempt < _MAX_RETRIES:
                        # Exponential backoff: 1s, 2s, 4s + jitter
                        delay = (
                            _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                            + random.uniform(0, 0.5)
                        )
                        logger.warning(
                            "OpenRouter: %s → %d (attempt %d/%d), retry in %.1fs",
                            model, exc.status, attempt, _MAX_RETRIES, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("OpenRouter: %s exhausted retries", model)

    raise GeminiUnavailableError(
        "AI is temporarily unavailable. Please try again in a moment."
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def send_text(system_prompt: str, user_message: str) -> dict:
    return await _request(
        _TEXT_MODELS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.4,
        max_tokens=2048,
    )


async def analyze_image(
    system_prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    user_note: Optional[str] = None,
) -> dict:
    instruction = "Analyze the food in this image."
    if user_note:
        instruction += f" User clarification: {user_note.strip()}"

    # Base64 внутри data URL — стандарт для vision через OpenAI-совместимый API
    b64 = base64.b64encode(image_bytes).decode()

    return await _request(
        _VISION_MODELS,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                    {"type": "text", "text": instruction},
                ],
            },
        ],
        temperature=0.2,
        max_tokens=4096,
    )
