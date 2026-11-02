import re
from typing import Any, Dict


def parse_query_offline(query: str) -> Dict[str, Any]:
    """
    Offline regex/keyword parser extracting user.* facts from free text.
    Provides reliable, zero-latency extraction with no network or API keys.
    """
    text = query.lower()
    facts: Dict[str, Any] = {}

    # 1. Meal Type
    if "breakfast" in text:
        facts["user.meal_type"] = "Breakfast"
    elif "lunch" in text:
        facts["user.meal_type"] = "Lunch"
    elif "dinner" in text or "supper" in text:
        facts["user.meal_type"] = "Dinner"
    elif "snack" in text:
        facts["user.meal_type"] = "Snack"

    # 2. Goals
    if "lose weight" in text or "weight loss" in text or "slimming" in text or "cut" in text:
        facts["user.goal"] = "weight_loss"
    elif "gain weight" in text or "weight gain" in text:
        facts["user.goal"] = "weight_gain"
    elif "muscle gain" in text or "build muscle" in text or "bulk" in text:
        facts["user.goal"] = "muscle_gain"
    elif "maintain" in text or "maintenance" in text:
        facts["user.goal"] = "maintain"
    elif "heart health" in text or "cardio" in text:
        facts["user.goal"] = "heart_health"
    elif "blood sugar" in text or "glucose" in text:
        facts["user.goal"] = "blood_sugar_control"

    # 3. Conditions
    conditions = []
    if "blood pressure" in text or "hypertension" in text or "high bp" in text:
        conditions.append("hypertension")
    if "diabetes" in text or "diabetic" in text or "type 2" in text or "type2" in text:
        conditions.append("type2_diabetes")
    if "cholesterol" in text:
        conditions.append("high_cholesterol")
    if conditions:
        facts["user.conditions"] = conditions

    # 4. Diet
    diet = []
    if "vegan" in text or "plant-based" in text:
        diet.append("vegan")
    elif "vegetarian" in text or "veggie" in text:
        diet.append("vegetarian")

    if "no beef" in text or "without beef" in text or "beef-free" in text:
        diet.append("no_beef")
    if "no pork" in text or "without pork" in text or "pork-free" in text:
        diet.append("no_pork")

    if diet:
        facts["user.diet"] = diet

    # 5. Age
    age_match = re.search(r"\b(?:age|aged)\s*(\d{1,2})\b", text)
    if not age_match:
        age_match = re.search(r"\b(\d{1,2})\s*(?:years?\s*old|yo)\b", text)
    if age_match:
        facts["user.age"] = float(age_match.group(1))

    # 6. Sex
    if re.search(r"\b(male|man|boy)\b", text) and not re.search(r"\b(female|woman)\b", text):
        facts["user.sex"] = "male"
    elif re.search(r"\b(female|woman|girl)\b", text):
        facts["user.sex"] = "female"

    return facts

