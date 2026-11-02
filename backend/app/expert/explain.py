from typing import Any, Dict, List, Optional
from app.expert.knowledge_base import KnowledgeBase, get_knowledge_base
from app.expert.schemas import Question


def build_how_explanation(
    food: Dict[str, Any],
    phase_b_fired_rules: List[Dict[str, Any]],
    phase_c_fired_rules: List[Dict[str, Any]],
    cf_history: List[float],
) -> List[str]:
    """
    Constructs a structured 'how' explanation for a single food item:
    - Classification rule tags (Phase B)
    - Recommendation rule scores and reasons (Phase C)
    - Combined certainty progression
    """
    how_lines: List[str] = []

    # Phase B: Tags applied
    for entry in phase_b_fired_rules:
        rule_id = entry.get("rule", "")
        change = entry.get("change", "")
        how_lines.append(f"{rule_id} -> {change}")

    # Phase C: Recommendation rules fired
    for entry in phase_c_fired_rules:
        rule_id = entry.get("rule", "")
        change = entry.get("change", "")
        cf_val = entry.get("cf", "")
        how_lines.append(f"{rule_id} (cf {cf_val}): {change}")

    # Certainty combination progression
    if cf_history:
        steps_str = " -> ".join(f"{h:g}" for h in cf_history)
        how_lines.append(f"Combined certainty: {steps_str}")

    return how_lines


def build_why_question_explanation(question: Question, kb: Optional[KnowledgeBase] = None) -> Dict[str, Any]:
    """
    Builds the explanation for why a question is asked in the consultation wizard:
    includes the question's 'why' rationale plus the exact rule IDs that read that fact.
    """
    kb = kb or get_knowledge_base()
    reading_rules = kb.fact_to_reading_rules.get(question.fact, [])
    return {
        "question_id": question.id,
        "fact": question.fact,
        "why": question.why,
        "dependent_rules": reading_rules,
    }


def explain_why_not(
    food: Dict[str, Any],
    constraints: Dict[str, Any],
    phase_a_trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Answers: 'Why is food X not in my recommended results?'
    Checks each active constraint and identifies the first failing rule.
    """
    name = food.get("name", "Unknown Food")

    # Map constraint fields to the rule that set or tightened them in Phase A trace
    rule_map: Dict[str, str] = {}
    for entry in phase_a_trace:
        r_id = entry.get("rule", "")
        ch = entry.get("change", "")
        if "max_calories" in ch:
            rule_map["max_calories"] = r_id
        if "min_calories" in ch:
            rule_map["min_calories"] = r_id
        if "max_sodium" in ch:
            rule_map["max_sodium"] = r_id
        if "min_protein" in ch:
            rule_map["min_protein"] = r_id
        if "max_sugars" in ch:
            rule_map["max_sugars"] = r_id
        if "max_carbs" in ch:
            rule_map["max_carbs"] = r_id
        if "max_fat" in ch:
            rule_map["max_fat"] = r_id
        if "max_cholesterol" in ch:
            rule_map["max_cholesterol"] = r_id
        if "min_fiber" in ch:
            rule_map["min_fiber"] = r_id
        if "exclude keywords" in ch:
            rule_map["exclude_keywords"] = r_id

    # 1. Calories
    max_c = constraints.get("max_calories")
    if max_c is not None and food.get("calories", 0) > max_c:
        r = rule_map.get("max_calories", "constraint rule")
        return {
            "food_name": name,
            "included": False,
            "reason": f"Calories ({food['calories']} kcal) exceeds your limit of {max_c} kcal set by rule {r}.",
            "failing_constraint": "max_calories",
            "violating_value": food["calories"],
            "threshold": max_c,
            "rule_id": r,
        }

    min_c = constraints.get("min_calories")
    if min_c is not None and food.get("calories", 0) < min_c:
        r = rule_map.get("min_calories", "constraint rule")
        return {
            "food_name": name,
            "included": False,
            "reason": f"Calories ({food['calories']} kcal) is below your minimum threshold of {min_c} kcal set by rule {r}.",
            "failing_constraint": "min_calories",
            "violating_value": food["calories"],
            "threshold": min_c,
            "rule_id": r,
        }

    # 2. Sodium
    max_na = constraints.get("max_sodium")
    if max_na is not None and food.get("sodium_mg", 0) > max_na:
        r = rule_map.get("max_sodium", "constraint rule")
        return {
            "food_name": name,
            "included": False,
            "reason": f"Sodium ({food['sodium_mg']} mg) exceeds your limit of {max_na} mg set by rule {r}.",
            "failing_constraint": "max_sodium",
            "violating_value": food["sodium_mg"],
            "threshold": max_na,
            "rule_id": r,
        }

    # 3. Protein
    min_p = constraints.get("min_protein")
    if min_p is not None and food.get("protein_g", 0) < min_p:
        r = rule_map.get("min_protein", "constraint rule")
        return {
            "food_name": name,
            "included": False,
            "reason": f"Protein ({food['protein_g']} g) is below required minimum of {min_p} g set by rule {r}.",
            "failing_constraint": "min_protein",
            "violating_value": food["protein_g"],
            "threshold": min_p,
            "rule_id": r,
        }

    # 4. Sugars
    max_s = constraints.get("max_sugars")
    if max_s is not None and food.get("sugars_g", 0) > max_s:
        r = rule_map.get("max_sugars", "constraint rule")
        return {
            "food_name": name,
            "included": False,
            "reason": f"Sugars ({food['sugars_g']} g) exceeds your limit of {max_s} g set by rule {r}.",
            "failing_constraint": "max_sugars",
            "violating_value": food["sugars_g"],
            "threshold": max_s,
            "rule_id": r,
        }

    # 5. Exclude keywords
    name_lower = name.lower()
    for word in constraints.get("exclude_keywords", []):
        if f" {word.lower()} " in f" {name_lower} ":
            r = rule_map.get("exclude_keywords", "diet rule")
            return {
                "food_name": name,
                "included": False,
                "reason": f"Food name contains excluded word '{word}' from diet rule {r}.",
                "failing_constraint": "exclude_keywords",
                "violating_value": word,
                "threshold": None,
                "rule_id": r,
            }

    return {
        "food_name": name,
        "included": True,
        "reason": "This food satisfies all derived constraints.",
        "failing_constraint": None,
        "violating_value": None,
        "threshold": None,
        "rule_id": None,
    }

