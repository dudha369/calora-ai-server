"""
Генерация еженедельных квестов через Gemini.
"""

from ai.gemini import send_text

QUESTS_PROMPT = """
You are a gamification engine for a nutrition app.
Generate exactly 3 weekly quests personalized for the user.
Quests must be achievable, specific, and based on recent eating patterns.

Quest difficulty: easy / medium / hard.
Quest types: protein_goal, streak, photo_log, hydration, calorie_goal.

Return ONLY valid JSON:
{
  "quests": [
    {
      "quest_key":   "protein_goal",
      "title":       "Белковая неделя",
      "description": "Достигни цели по белку 5 дней из 7",
      "icon":        "💪",
      "target_value": 5,
      "expires_days": 7
    }
  ]
}
"""


async def generate_weekly_quests(profile_summary: dict) -> list[dict]:
    """
    profile_summary: {goal_type, activity_level, current_streak,
                      avg_calories_7d, avg_protein_7d, avg_water_7d}
    Возвращает список из 3 квестов.
    """
    user_msg = str(profile_summary)
    result = await send_text(QUESTS_PROMPT, user_msg)
    return result.get("quests", [])
