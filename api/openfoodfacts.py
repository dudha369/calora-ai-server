"""
GET  /api/openfoodfacts/status — доступна ли отправка правок (сервисный аккаунт настроен)
POST /api/openfoodfacts/submit — добавить новый товар или предложить правку существующего
                                   (общий эндпоинт OFF сам разберётся по штрихкоду)
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from .utils import get_current_user, check_rate_limit
from db import User
from services.openfoodfacts import submit_product, is_configured

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/openfoodfacts", tags=["openfoodfacts"])

MAX_SUBMIT_PER_MINUTE = 5
_BARCODE_RE = re.compile(r"^\d{6,14}$")


class ProductSubmitIn(BaseModel):
    barcode: str
    product_name: str = Field(min_length=1, max_length=200)
    brand: Optional[str] = Field(default=None, max_length=100)
    portion_g: float = Field(gt=0, le=5000)
    calories: float = Field(ge=0, le=9000)
    protein_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=1000)
    fiber_g: float = Field(ge=0, le=1000)
    sugar_g: float = Field(ge=0, le=1000)


@router.get("/status")
async def status():
    """Позволяет фронту скрыть кнопки add/edit, если фича не настроена."""
    return {"available": is_configured()}


@router.post("/submit")
async def submit(body: ProductSubmitIn, user: User = Depends(get_current_user)):
    if not _BARCODE_RE.match(body.barcode):
        raise HTTPException(status_code=400, detail="Invalid barcode")

    check_rate_limit(
        user.telegram_id, bucket="off_submit", max_per_minute=MAX_SUBMIT_PER_MINUTE
    )

    if not is_configured():
        raise HTTPException(
            status_code=503, detail="Product submission is currently unavailable"
        )

    ok = await submit_product(
        barcode=body.barcode,
        product_name=body.product_name,
        brand=body.brand,
        portion_g=body.portion_g,
        calories=body.calories,
        protein_g=body.protein_g,
        fat_g=body.fat_g,
        carbs_g=body.carbs_g,
        fiber_g=body.fiber_g,
        sugar_g=body.sugar_g,
        comment=f"Submitted via Calora AI (user {user.telegram_id})",
    )
    if not ok:
        raise HTTPException(
            status_code=502, detail="OpenFoodFacts rejected the submission"
        )

    return {"ok": True}
