"""
Генерация ежедневного совета по итогам питания.
"""

from ai.gemini import send_text

TIPS_PROMPT = """
You are a friendly nutrition coach for a calorie tracking app.
You receive today's food log summary and user goals.
Give ONE actionable, personalized tip based on what the user actually ate.

Be specific, not generic. Reference actual numbers from the log.
Use friendly, motivating tone in Russian. Never be preachy.

Return ONLY valid JSON:
{
  "tip": "Ты сегодня хорошо набрал белок! Но калории на 400 выше нормы — завтра попробуй заменить майонез в салате на греческий йогурт, сэкономишь ~120 ккал.",
  "tip_type": "macro_balance",
  "icon": "🥗"
}

tip_type options: hydration, macro_balance, overeating, undereating,
food_quality, streak_praise
"""


async def generate_daily_tip(goals: dict, today_summary: dict) -> dict:
    """
    goals:         {calories, protein_g, fat_g, carbs_g, water_ml}
    today_summary: {total_calories, total_protein_g, total_fat_g,
                    total_carbs_g, total_water_ml, food_names: [...]}
    Возвращает: {"tip", "tip_type", "icon"}
    """
    user_msg = str({"goals": goals, "today": today_summary})
    return await send_text(TIPS_PROMPT, user_msg)
