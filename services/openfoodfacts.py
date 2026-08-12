"""
Запись в Open Food Facts от имени сервисного аккаунта Calora AI.

OFF требует авторизованный аккаунт для правок/добавления товаров (write API
world.openfoodfacts.org/cgi/product_jqm2.pl, form-data). Не заводим аккаунт
на каждого пользователя — шлём от одного сервисного, с пометкой в комментарии.
Один и тот же вызов OFF обслуживает и создание нового товара, и правку
существующего — определяется по коду штрихкода на их стороне.

Если OFF_USER_ID/OFF_PASSWORD не заданы — фича тихо выключена (is_configured()).
"""

import logging
from typing import Optional

import httpx

from config import config

logger = logging.getLogger(__name__)

OFF_WRITE_URL = "https://world.openfoodfacts.org/cgi/product_jqm2.pl"
REQUEST_TIMEOUT = 15


def is_configured() -> bool:
    return bool(config.OFF_USER_ID and config.OFF_PASSWORD.get_secret_value())


def _scale_to_100g(value: float, portion_g: float) -> float:
    """Пользователь вводит значения на введённую порцию (как везде в UI —
    см. NutritionEditGrid); OFF хранит нутриенты на 100г."""
    if portion_g <= 0:
        return value
    return round(value * 100 / portion_g, 2)


async def submit_product(
    barcode: str,
    product_name: str,
    portion_g: float,
    calories: float,
    protein_g: float,
    fat_g: float,
    carbs_g: float,
    fiber_g: float,
    sugar_g: float,
    brand: Optional[str] = None,
    comment: Optional[str] = None,
) -> bool:
    if not is_configured():
        raise RuntimeError("OpenFoodFacts write access is not configured")

    data = {
        "code": barcode,
        "user_id": config.OFF_USER_ID,
        "password": config.OFF_PASSWORD.get_secret_value(),
        "product_name": product_name,
        "serving_size": f"{portion_g} g",
        "nutriment_energy-kcal": _scale_to_100g(calories, portion_g),
        "nutriment_energy-kcal_unit": "kcal",
        "nutriment_proteins": _scale_to_100g(protein_g, portion_g),
        "nutriment_proteins_unit": "g",
        "nutriment_fat": _scale_to_100g(fat_g, portion_g),
        "nutriment_fat_unit": "g",
        "nutriment_carbohydrates": _scale_to_100g(carbs_g, portion_g),
        "nutriment_carbohydrates_unit": "g",
        "nutriment_sugars": _scale_to_100g(sugar_g, portion_g),
        "nutriment_sugars_unit": "g",
        "nutriment_fiber": _scale_to_100g(fiber_g, portion_g),
        "nutriment_fiber_unit": "g",
        "comment": comment or "Submitted via Calora AI",
    }
    if brand:
        data["brands"] = brand

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(OFF_WRITE_URL, data=data)
            resp.raise_for_status()
            result = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("OFF submit failed for barcode %s: %s", barcode, e)
        return False

    ok = result.get("status") == 1 or result.get("status_verbose") == "fields saved"
    if not ok:
        logger.warning("OFF submit rejected for barcode %s: %s", barcode, result)
    return ok
