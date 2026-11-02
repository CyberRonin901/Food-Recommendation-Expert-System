import sqlite3
from typing import Any, Dict, List, Optional
from app.expert.engine import run_forward_chaining
from app.expert.explain import build_how_explanation
from app.expert.knowledge_base import get_knowledge_base
from app.expert.memory import WorkingMemory
from app.expert.offline_parser import parse_query_offline
from app.filters import build_filter_query
from app.schemas import (
    ConsultFoodResult,
    ConsultRequest,
    ConsultResponse,
    Preferences,
)


def normalize_facts_dict(raw_facts: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizes facts dict keys so they all carry their namespace (e.g. 'user.goal')."""
    normalized = {}
    for k, v in raw_facts.items():
        if v is None:
            continue
        if k in ("goal", "meal_type", "conditions", "diet", "want_calorie_target", "age", "sex", "height_cm", "weight_kg", "activity_level"):
            normalized[f"user.{k}"] = v
        else:
            normalized[k] = v
    return normalized


def consult(request: ConsultRequest, conn: sqlite3.Connection) -> ConsultResponse:
    kb = get_knowledge_base()

    # Step 1: Gather facts from query if provided, then merge with request facts (request facts win)
    merged_facts: Dict[str, Any] = {}
    if request.query and request.query.strip():
        extracted_facts = parse_query_offline(request.query.strip())
        merged_facts.update(extracted_facts)

    if request.facts:
        norm_user_facts = normalize_facts_dict(request.facts)
        merged_facts.update(norm_user_facts)

    # Step 2: Initialize Working Memory for Phase A
    memory = WorkingMemory(initial_facts=merged_facts)

    # Step 3: Phase A (layers 00_derived, 01_constraints, 04_safety)
    phase_a_rules = kb.get_phase_a_rules()
    phase_a_trace = run_forward_chaining(phase_a_rules, memory)

    # Step 4: Contradiction Check (T2.8)
    min_c = memory.constraints.get("min_calories")
    max_c = memory.constraints.get("max_calories")
    if min_c is not None and max_c is not None and min_c > max_c:
        memory.constraints["min_calories"] = None
        memory.facts["constraint.min_calories"] = None
        memory.add_warning(
            f"Contradiction detected: min_calories ({min_c:g}) was greater than max_calories ({max_c:g}). Relaxed minimum calorie constraint."
        )

    # Step 5: Convert constraints to Preferences for SQL filtering
    pref_kwargs = {
        "meal_type": memory.get_fact("user.meal_type"),
        "min_calories": memory.constraints.get("min_calories"),
        "max_calories": memory.constraints.get("max_calories"),
        "min_protein": memory.constraints.get("min_protein"),
        "max_carbs": memory.constraints.get("max_carbs"),
        "max_fat": memory.constraints.get("max_fat"),
        "min_fiber": memory.constraints.get("min_fiber"),
        "max_sugars": memory.constraints.get("max_sugars"),
        "max_sodium": memory.constraints.get("max_sodium"),
        "max_cholesterol": memory.constraints.get("max_cholesterol"),
        "exclude_keywords": memory.constraints.get("exclude_keywords"),
        "goals": memory.constraints.get("goals"),
        "include_condiments": False,
    }
    # Clean None values
    clean_prefs = Preferences(**{k: v for k, v in pref_kwargs.items() if v is not None and v != []})

    where_sql, params = build_filter_query(clean_prefs)
    query_sql = f"SELECT * FROM foods {where_sql}"

    cursor = conn.cursor()
    cursor.execute(query_sql, params)
    raw_rows = [dict(r) for r in cursor.fetchall()]

    if not raw_rows:
        active_limits = []
        for lim_name in ("max_calories", "min_calories", "min_protein", "max_carbs", "max_fat", "min_fiber", "max_sugars", "max_sodium", "max_cholesterol"):
            v = memory.constraints.get(lim_name)
            if v is not None:
                active_limits.append(f"{lim_name} ({v:g})")

        no_match_msg = "No foods match your search criteria."
        if active_limits:
            no_match_msg += f" Try relaxing: {', '.join(active_limits)}."

        warnings = list(memory.constraints.get("warnings", []))
        warnings.append(no_match_msg)

        return ConsultResponse(
            constraints=dict(memory.constraints),
            warnings=warnings,
            phase_a_trace=phase_a_trace,
            total_matches=0,
            results=[],
        )

    # Step 6: Phases B & C per candidate food
    phase_b_rules = kb.get_phase_b_rules()
    phase_c_rules = kb.get_phase_c_rules()

    has_active_goals = bool(memory.constraints.get("goals"))
    evaluated_foods: List[Dict[str, Any]] = []

    for food in raw_rows:
        # Construct food-specific working memory
        food_facts = dict(memory.facts)
        for nutrient in (
            "calories", "protein_g", "carbs_g", "fat_g", "fiber_g",
            "sugars_g", "sodium_mg", "cholesterol_mg", "category_main", "meal_type"
        ):
            food_facts[f"food.{nutrient}"] = food[nutrient]

        f_mem = WorkingMemory(initial_facts=food_facts)
        # Copy active constraints
        f_mem.constraints = dict(memory.constraints)

        # Run Phase B (Tagging)
        b_trace = run_forward_chaining(phase_b_rules, f_mem)

        # Run Phase C (Recommendation Scoring)
        c_trace = run_forward_chaining(phase_c_rules, f_mem)

        food_tags = sorted(list(f_mem.tags))

        if has_active_goals or c_trace:
            final_cf = f_mem.cf
            final_score = round(50.0 * (final_cf + 1.0), 1)
        else:
            final_cf = None
            final_score = None

        how_lines = build_how_explanation(food, b_trace, c_trace, f_mem.cf_history)

        food_item = dict(food)
        food_item["cf"] = final_cf
        food_item["score"] = final_score
        food_item["tags"] = food_tags
        food_item["how"] = how_lines
        evaluated_foods.append(food_item)

    # Step 7: Rank and Deduplicate
    if has_active_goals:
        evaluated_foods.sort(
            key=lambda x: (
                -(x["score"] if x["score"] is not None else -1.0),
                -(x.get("pct_protein", 0.0)),
                -x["protein_g"],
                x["name"],
            )
        )
    else:
        evaluated_foods.sort(key=lambda x: x["name"])

    seen_names = set()
    deduped_results: List[Dict[str, Any]] = []
    for f in evaluated_foods:
        if f["name"] not in seen_names:
            seen_names.add(f["name"])
            deduped_results.append(f)

    total_matches = len(deduped_results)
    top_k = request.top_k or 10
    top_results = deduped_results[:top_k]

    final_results = [
        ConsultFoodResult(
            id=f.get("id"),
            name=f["name"],
            calories=float(f["calories"]),
            protein_g=float(f["protein_g"]),
            carbs_g=float(f["carbs_g"]),
            fat_g=float(f["fat_g"]),
            fiber_g=float(f["fiber_g"]),
            sugars_g=float(f["sugars_g"]),
            sodium_mg=float(f["sodium_mg"]),
            cholesterol_mg=float(f["cholesterol_mg"]),
            category=f.get("category"),
            meal_type=f.get("meal_type"),
            cf=f.get("cf"),
            score=f.get("score"),
            tags=f.get("tags", []),
            how=f.get("how", []),
        )
        for f in top_results
    ]

    warnings = list(memory.constraints.get("warnings", []))
    if not has_active_goals:
        warnings.append("No goals were set, so results are sorted alphabetically without ranking scores.")

    return ConsultResponse(
        constraints=dict(memory.constraints),
        warnings=warnings,
        phase_a_trace=phase_a_trace,
        total_matches=total_matches,
        results=final_results,
    )

