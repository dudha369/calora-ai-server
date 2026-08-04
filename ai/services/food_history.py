"""
Компактный текстовый дайджест последних приёмов пищи пользователя —
подмешивается в промпт текстового/голосового анализа, чтобы ИИ мог понимать
ссылки вида "как вчера" / "тот же завтрак" и переиспользовать точные КБЖУ
уже залогированных блюд вместо повторной оценки с нуля.

Единственный AI-сервис, которому нужен прямой доступ к БД (остальные
работают чисто на байтах/тексте) — это оправдано: без истории функция
"как вчера" физически невозможна. Доступ read-only.
"""

from datetime import date, timedelta
from typing import Optional

from db import FoodLog

HISTORY_DAYS = 7
MAX_HISTORY_LOGS = 20


async def build_recent_food_history(user_id: int, today: Optional[date] = None) -> str:
    """
    Возвращает блок текста для добавления к системному промпту, либо ""
    если истории нет. Метки времени и инструкция — на английском намеренно:
    это служебный контекст для модели, а не то, что видит пользователь,
    и не должно зависеть от языка приложения.
    """
    today = today or date.today()
    since = today - timedelta(days=HISTORY_DAYS)

    logs = (
        await FoodLog.filter(user_id=user_id, log_date__gte=since, log_date__lt=today)
        .order_by("-log_date")
        .limit(MAX_HISTORY_LOGS)
        .prefetch_related("items")
    )
    if not logs:
        return ""

    lines = []
    for log in logs:
        days_ago = (today - log.log_date).days
        label = (
            "Yesterday"
            if days_ago == 1
            else f"{days_ago} days ago ({log.log_date.isoformat()})"
        )
        items_str = ", ".join(f"{i.food_name} {i.portion_g}g" for i in log.items)
        if items_str:
            lines.append(f"{label}: {items_str}")

    if not lines:
        return ""

    return (
        "\n\nUser's recent food log, for reference only — use it ONLY if the "
        'description explicitly references a past meal (e.g. "like yesterday", '
        '"same as before", "my usual"). In that case: reuse the exact matching '
        "entry's macros rather than re-estimating, set confidence high (0.9+) "
        "for those items, and do NOT set ask_user for them — reusing a known "
        "logged entry is not an ambiguous estimate. If the description does not "
        "reference a past meal, ignore this list completely:\n" + "\n".join(lines)
    )
