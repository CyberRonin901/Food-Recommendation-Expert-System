import sqlite3
from typing import Any, Dict, List, Optional
from app.explain import generate_reasons
from app.filters import build_filter_query
from app.llm import extract_preferences_from_query
from app.schemas import FoodResult, Preferences, RecommendRequest, RecommendResponse
from app.scoring import score_and_rank_foods


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

    # Step 1: If free-text query is provided, call LLM
    if request.query and request.query.strip():
        extracted, warn = extract_preferences_from_query(request.query.strip())
        if warn:
            warnings.append(warn)
        llm_prefs = extracted

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

