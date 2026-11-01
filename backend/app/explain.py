from typing import Any, Dict, List
from app.filters import normalize_keyword
from app.schemas import Preferences


def generate_reasons(row: Dict[str, Any], prefs: Preferences) -> List[str]:
    reasons: List[str] = []

    # 1. Goal reasons
    if prefs.goals:
        for goal in prefs.goals:
            if goal == "high_protein":
                pct = int(round(row["pct_protein"] * 100))
                reasons.append(f"High protein: {row['protein_g']:g} g (higher than {pct}% of foods)")
            elif goal == "high_fiber":
                pct = int(round(row["pct_fiber"] * 100))
                reasons.append(f"High fiber: {row['fiber_g']:g} g (higher than {pct}% of foods)")
            elif goal == "low_carbs":
                pct = int(round((1.0 - row["pct_carbs"]) * 100))
                reasons.append(f"Low carbs: {row['carbs_g']:g} g (lower than {pct}% of foods)")
            elif goal == "low_fat":
                pct = int(round((1.0 - row["pct_fat"]) * 100))
                reasons.append(f"Low fat: {row['fat_g']:g} g (lower than {pct}% of foods)")
            elif goal == "low_sugar":
                pct = int(round((1.0 - row["pct_sugars"]) * 100))
                reasons.append(f"Low sugar: {row['sugars_g']:g} g (lower than {pct}% of foods)")
            elif goal == "low_sodium":
                pct = int(round((1.0 - row["pct_sodium"]) * 100))
                reasons.append(f"Low sodium: {row['sodium_mg']:g} mg (lower than {pct}% of foods)")
            elif goal == "low_cholesterol":
                pct = int(round((1.0 - row["pct_cholesterol"]) * 100))
                reasons.append(f"Low cholesterol: {row['cholesterol_mg']:g} mg (lower than {pct}% of foods)")

    # 2. Limit reasons (show prominent limits if present)
    if prefs.max_calories is not None:
        reasons.append(f"{row['calories']:g} kcal, within your {prefs.max_calories:g} kcal limit")
    if prefs.min_protein is not None:
        reasons.append(f"{row['protein_g']:g} g protein, meeting your {prefs.min_protein:g} g minimum")
    if prefs.max_carbs is not None:
        reasons.append(f"{row['carbs_g']:g} g carbs, within your {prefs.max_carbs:g} g limit")
    if prefs.max_fat is not None:
        reasons.append(f"{row['fat_g']:g} g fat, within your {prefs.max_fat:g} g limit")
    if prefs.min_fiber is not None:
        reasons.append(f"{row['fiber_g']:g} g fiber, meeting your {prefs.min_fiber:g} g minimum")
    if prefs.max_sugars is not None:
        reasons.append(f"{row['sugars_g']:g} g sugars, within your {prefs.max_sugars:g} g limit")
    if prefs.max_sodium is not None:
        reasons.append(f"{row['sodium_mg']:g} mg sodium, within your {prefs.max_sodium:g} mg limit")
    if prefs.max_cholesterol is not None:
        reasons.append(f"{row['cholesterol_mg']:g} mg cholesterol, within your {prefs.max_cholesterol:g} mg limit")

    # 3. Keyword matches
    if prefs.include_keywords:
        name_search = row.get("name_search", "")
        for word in prefs.include_keywords:
            w_norm = normalize_keyword(word)
            if w_norm and f" {w_norm} " in name_search:
                reasons.append(f"Name contains '{word}'")

    # 4. Meal type
    if prefs.meal_type:
        reasons.append(f"Listed as a {row['meal_type']} food")

    return reasons
