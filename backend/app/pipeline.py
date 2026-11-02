import sqlite3
from typing import Any, Dict, List, Optional
from app.explain import generate_reasons
from app.filters import build_filter_query
from app.llm import extract_preferences_from_query
from app.schemas import FoodResult, Preferences, RecommendRequest, RecommendResponse
from app.scoring import score_and_rank_foods


# Mapping from user-level goals (extracted by offline parser) to nutrient-level goals
# used by the scoring system.
USER_GOAL_TO_NUTRIENT_GOALS: Dict[str, List[str]] = {
    "weight_loss": ["high_protein", "high_fiber"],
    "muscle_gain": ["high_protein"],
    "weight_gain": ["high_protein"],
    "heart_health": ["low_sodium", "low_cholesterol", "low_fat", "high_fiber"],
    "blood_sugar_control": ["low_sugar", "high_fiber", "low_carbs"],
    "maintain": ["high_protein", "high_fiber"],
}


def parse_query_for_recommend(query: str) -> Preferences:
    """
    Offline keyword/regex parser for the /api/recommend endpoint.
    Extracts meal type, goals, and keywords from free text without an LLM.
    Maps user-level intent (e.g. 'weight loss') to nutrient-level goals.
    """
    text = query.lower()
    kwargs: Dict[str, Any] = {}

    # 1. Meal Type
    if "breakfast" in text:
        kwargs["meal_type"] = "Breakfast"
    elif "lunch" in text:
        kwargs["meal_type"] = "Lunch"
    elif "dinner" in text or "supper" in text:
        kwargs["meal_type"] = "Dinner"
    elif "snack" in text:
        kwargs["meal_type"] = "Snack"

    # 2. Goals — map from user-level intent to nutrient-level goals
    goals: List[str] = []

    if "lose weight" in text or "weight loss" in text or "slimming" in text or "diet" in text:
        goals.extend(USER_GOAL_TO_NUTRIENT_GOALS["weight_loss"])
    elif "gain weight" in text or "weight gain" in text:
        goals.extend(USER_GOAL_TO_NUTRIENT_GOALS["weight_gain"])
    elif "muscle" in text or "bulk" in text:
        goals.extend(USER_GOAL_TO_NUTRIENT_GOALS["muscle_gain"])
    elif "heart" in text or "cardio" in text:
        goals.extend(USER_GOAL_TO_NUTRIENT_GOALS["heart_health"])
    elif "blood sugar" in text or "diabetic" in text or "diabetes" in text:
        goals.extend(USER_GOAL_TO_NUTRIENT_GOALS["blood_sugar_control"])

    # Direct nutrient-goal keywords
    if "high protein" in text or "protein rich" in text:
        goals.append("high_protein")
    if "high fiber" in text or "high fibre" in text or "fiber rich" in text:
        goals.append("high_fiber")
    if "low carb" in text:
        goals.append("low_carbs")
    if "low fat" in text:
        goals.append("low_fat")
    if "low sugar" in text or "no sugar" in text or "sugar free" in text:
        goals.append("low_sugar")
    if "low sodium" in text or "low salt" in text:
        goals.append("low_sodium")
    if "low cholesterol" in text:
        goals.append("low_cholesterol")
    if "healthy" in text or "clean eating" in text:
        goals.extend(["high_protein", "high_fiber"])

    # Deduplicate goals preserving order
    if goals:
        seen = set()
        unique_goals: List[str] = []
        for g in goals:
            if g not in seen:
                seen.add(g)
                unique_goals.append(g)
        kwargs["goals"] = unique_goals

    # 3. Exclude keywords
    exclude: List[str] = []
    if "no chicken" in text or "without chicken" in text:
        exclude.append("chicken")
    if "no beef" in text or "without beef" in text:
        exclude.append("beef")
    if "no pork" in text or "without pork" in text:
        exclude.append("pork")
    if "no fish" in text or "without fish" in text:
        exclude.append("fish")
    if "vegetarian" in text or "veggie" in text:
        exclude.extend(["chicken", "beef", "pork", "lamb", "turkey", "duck", "fish",
                         "salmon", "tuna", "shrimp", "bacon", "ham", "sausage", "steak", "meat"])
    if "vegan" in text:
        exclude.extend(["chicken", "beef", "pork", "lamb", "turkey", "duck", "fish",
                         "salmon", "tuna", "shrimp", "bacon", "ham", "sausage", "steak", "meat",
                         "milk", "cheese", "butter", "yogurt", "egg", "cream", "honey"])
    if exclude:
        seen_ex = set()
        unique_ex: List[str] = []
        for e in exclude:
            if e not in seen_ex:
                seen_ex.add(e)
                unique_ex.append(e)
        kwargs["exclude_keywords"] = unique_ex

    # 4. Calorie limits from text
    import re
    cal_match = re.search(r"under\s+(\d+)\s*(?:cal|kcal|calories)", text)
    if cal_match:
        kwargs["max_calories"] = float(cal_match.group(1))

    return Preferences(**kwargs)


def merge_preferences(form_req: RecommendRequest, llm_prefs: Optional[Preferences]) -> Preferences:
    """
    Merges form preferences and LLM-extracted preferences.
    Form values take precedence over LLM values.
    """
    def choose(field_name: str, default: Any = None) -> Any:
        form_val = getattr(form_req, field_name, None)
        if form_val is not None:
            return form_val
        if llm_prefs is not None:
            llm_val = getattr(llm_prefs, field_name, None)
            if llm_val is not None:
                return llm_val
        return default

    # For lists: if empty list [] was passed in form, treat as None or empty
    def choose_list(field_name: str) -> Optional[List[Any]]:
        form_val = getattr(form_req, field_name, None)
        if form_val is not None and len(form_val) > 0:
            return form_val
        if llm_prefs is not None:
            llm_val = getattr(llm_prefs, field_name, None)
            if llm_val is not None and len(llm_val) > 0:
                return llm_val
        if form_val is not None:
            return form_val
        return None

    top_k_val = choose("top_k", 10)
    if top_k_val is None:
        top_k_val = 10

    merged = Preferences(
        meal_type=choose("meal_type"),
        categories=choose_list("categories"),
        goals=choose_list("goals"),
        include_keywords=choose_list("include_keywords"),
        exclude_keywords=choose_list("exclude_keywords"),
        include_condiments=choose("include_condiments", False),
        min_calories=choose("min_calories"),
        max_calories=choose("max_calories"),
        min_protein=choose("min_protein"),
        max_carbs=choose("max_carbs"),
        max_fat=choose("max_fat"),
        min_fiber=choose("min_fiber"),
        max_sugars=choose("max_sugars"),
        max_sodium=choose("max_sodium"),
        max_cholesterol=choose("max_cholesterol"),
        top_k=top_k_val,
    )
    return merged


def recommend(request: RecommendRequest, conn: sqlite3.Connection) -> RecommendResponse:
    warnings: List[str] = []
    llm_prefs: Optional[Preferences] = None

    # Step 1: If free-text query is provided, try LLM first, then fallback to offline parser
    if request.query and request.query.strip():
        extracted, warn = extract_preferences_from_query(request.query.strip())
        if warn:
            warnings.append(warn)
        llm_prefs = extracted

        # Fallback: if LLM failed or returned no useful goals, use offline parser
        if llm_prefs is None or (not llm_prefs.goals and not llm_prefs.meal_type):
            offline_prefs = parse_query_for_recommend(request.query.strip())
            if llm_prefs is None:
                llm_prefs = offline_prefs
            else:
                # Merge: offline fills in what LLM missed
                if not llm_prefs.goals and offline_prefs.goals:
                    llm_prefs = llm_prefs.model_copy(update={"goals": offline_prefs.goals})
                if not llm_prefs.meal_type and offline_prefs.meal_type:
                    llm_prefs = llm_prefs.model_copy(update={"meal_type": offline_prefs.meal_type})
                if not llm_prefs.exclude_keywords and offline_prefs.exclude_keywords:
                    llm_prefs = llm_prefs.model_copy(update={"exclude_keywords": offline_prefs.exclude_keywords})
                if not llm_prefs.max_calories and offline_prefs.max_calories:
                    llm_prefs = llm_prefs.model_copy(update={"max_calories": offline_prefs.max_calories})

    # Step 2: Merge form values and LLM preferences
    prefs = merge_preferences(request, llm_prefs)

    # Step 3: Compute interpreted dictionary
    interpreted: Dict[str, Any] = {}
    for k, v in prefs.model_dump().items():
        if v is not None and v != [] and (k != "include_condiments" or v is True):
            interpreted[k] = v

    # Step 4: Build SQL query from hard filters
    where_sql, params = build_filter_query(prefs)
    query_sql = f"SELECT * FROM foods {where_sql}"

    cursor = conn.cursor()
    cursor.execute(query_sql, params)
    rows = [dict(r) for r in cursor.fetchall()]

    # Step 5: Check matches
    if not rows:
        active_limits = []
        for limit_attr in [
            "min_calories",
            "max_calories",
            "min_protein",
            "max_carbs",
            "max_fat",
            "min_fiber",
            "max_sugars",
            "max_sodium",
            "max_cholesterol",
        ]:
            val = getattr(prefs, limit_attr, None)
            if val is not None:
                active_limits.append(f"{limit_attr} ({val:g})")

        if active_limits:
            warnings.append(f"No foods match. Try relaxing: {', '.join(active_limits)}.")
        else:
            warnings.append("No foods match your search criteria.")

        return RecommendResponse(
            interpreted=interpreted,
            total_matches=0,
            results=[],
            warnings=warnings,
        )

    # Step 6: Rank foods using goal scores
    ranked_foods = score_and_rank_foods(rows, prefs)
    total_matches = len(ranked_foods)

    if not prefs.goals:
        warnings.append("No goals were selected, so results are sorted alphabetically without ranking scores.")

    top_k = prefs.top_k or 10
    top_results = ranked_foods[:top_k]

    # Step 7: Build result objects with templated reasons
    results: List[FoodResult] = []
    for food in top_results:
        reasons = generate_reasons(food, prefs)
        results.append(
            FoodResult(
                id=food["id"],
                name=food["name"],
                category=food["category"],
                meal_type=food["meal_type"],
                calories=float(food["calories"]),
                protein_g=float(food["protein_g"]),
                carbs_g=float(food["carbs_g"]),
                fat_g=float(food["fat_g"]),
                fiber_g=float(food["fiber_g"]),
                sugars_g=float(food["sugars_g"]),
                sodium_mg=float(food["sodium_mg"]),
                cholesterol_mg=float(food["cholesterol_mg"]),
                score=food.get("score"),
                reasons=reasons,
            )
        )

    return RecommendResponse(
        interpreted=interpreted,
        total_matches=total_matches,
        results=results,
        warnings=warnings,
    )

