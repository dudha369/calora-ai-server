"""Tests for the Mifflin–St Jeor goal calculator (pure math, no AI)."""

import pytest
from ai.services.goal_calculator import calculate_base_goals


def test_male_lose():
    """Male, 25y, 180cm, 80kg, moderate activity, goal=lose."""
    result = calculate_base_goals({
        "gender": "male",
        "age": 25,
        "height_cm": 180,
        "weight_kg": 80.0,
        "goal_type": "lose",
        "activity_level": "moderate",
    })
    # BMR = 10*80 + 6.25*180 - 5*25 + 5 = 800 + 1125 - 125 + 5 = 1805
    # TDEE = 1805 * 1.55 = 2797.75
    # Calories = 2797.75 - 500 = 2297.75 → 2298
    assert result["calories"] == 2298
    assert result["protein_g"] == 144.0  # 80 * 1.8
    assert result["water_ml"] == 2640    # max(80*33, 1500)

    # fat_g = round(2298 * 0.30 / 9, 1) = round(76.6, 1) = 76.6
    assert result["fat_g"] == 76.6
    # carbs_g = round((2298 - 144*4 - 76.6*9) / 4, 1)
    #         = round((2298 - 576 - 689.4) / 4, 1)
    #         = round(1032.6 / 4, 1) = round(258.15, 1) = 258.2
    assert result["carbs_g"] == 258.1


def test_female_maintain():
    """Female, 30y, 165cm, 60kg, light activity, goal=maintain."""
    result = calculate_base_goals({
        "gender": "female",
        "age": 30,
        "height_cm": 165,
        "weight_kg": 60.0,
        "goal_type": "maintain",
        "activity_level": "light",
    })
    # BMR = 10*60 + 6.25*165 - 5*30 - 161 = 600 + 1031.25 - 150 - 161 = 1320.25
    # TDEE = 1320.25 * 1.375 = 1815.34375 → 1815
    assert result["calories"] == 1815
    assert result["protein_g"] == 108.0  # 60 * 1.8
    assert result["water_ml"] == 1980    # max(60*33, 1500)


def test_gain():
    """Goal=gain adds +300 to TDEE."""
    result = calculate_base_goals({
        "gender": "male",
        "age": 20,
        "height_cm": 175,
        "weight_kg": 70.0,
        "goal_type": "gain",
        "activity_level": "active",
    })
    # BMR = 10*70 + 6.25*175 - 5*20 + 5 = 700 + 1093.75 - 100 + 5 = 1698.75
    # TDEE = 1698.75 * 1.725 = 2930.34375
    # Calories = 2930.34375 + 300 = 3230.34375 → 3230
    assert result["calories"] == 3230


def test_minimum_calories():
    """Calories should never go below 1200."""
    result = calculate_base_goals({
        "gender": "female",
        "age": 60,
        "height_cm": 150,
        "weight_kg": 45.0,
        "goal_type": "lose",
        "activity_level": "sedentary",
    })
    # BMR = 10*45 + 6.25*150 - 5*60 - 161 = 450 + 937.5 - 300 - 161 = 926.5
    # TDEE = 926.5 * 1.2 = 1111.8
    # Calories = 1111.8 - 500 = 611.8 → clamped to 1200
    assert result["calories"] == 1200


def test_minimum_water():
    """Water should never go below 1500ml."""
    result = calculate_base_goals({
        "gender": "female",
        "age": 25,
        "height_cm": 155,
        "weight_kg": 40.0,
        "goal_type": "maintain",
        "activity_level": "sedentary",
    })
    # 40 * 33 = 1320 → clamped to 1500
    assert result["water_ml"] == 1500


def test_unknown_activity_defaults_to_moderate():
    """Unknown activity_level falls back to 1.55 multiplier."""
    result = calculate_base_goals({
        "gender": "male",
        "age": 25,
        "height_cm": 180,
        "weight_kg": 80.0,
        "goal_type": "maintain",
        "activity_level": "unknown_level",
    })
    # Should use 1.55 (moderate) as fallback
    # BMR = 1805, TDEE = 1805 * 1.55 = 2797.75 → 2798
    assert result["calories"] == 2798
