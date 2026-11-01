from typing import Any, Dict, List, Optional
from app.schemas import Preferences


def compute_food_score(row: Dict[str, Any], goals: Optional[List[str]]) -> Optional[float]:
    if not goals:
        return None

    scores: List[float] = []
    for goal in goals:
        if goal == "high_protein":
            scores.append(float(row["pct_protein"]))
        elif goal == "high_fiber":
            scores.append(float(row["pct_fiber"]))
        elif goal == "low_carbs":
            scores.append(1.0 - float(row["pct_carbs"]))
        elif goal == "low_fat":
            scores.append(1.0 - float(row["pct_fat"]))
        elif goal == "low_sugar":
            scores.append(1.0 - float(row["pct_sugars"]))
        elif goal == "low_sodium":
            scores.append(1.0 - float(row["pct_sodium"]))
        elif goal == "low_cholesterol":
            scores.append(1.0 - float(row["pct_cholesterol"]))

    if not scores:
        return None

    mean_score = sum(scores) / len(scores)
    return round(100.0 * mean_score, 1)


def score_and_rank_foods(rows: List[Dict[str, Any]], prefs: Preferences) -> List[Dict[str, Any]]:
    """
    Computes scores for each food, sorts according to rules:
    - If goals: sort by score DESC, protein_g DESC, name ASC
    - If no goals: sort by name ASC
    Then deduplicates by food name, preserving the highest-ranked entry.
    """
    has_goals = bool(prefs.goals)

    scored_items: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["score"] = compute_food_score(item, prefs.goals) if has_goals else None
        scored_items.append(item)

    if has_goals:
        # Sort by score DESC, protein_g DESC, name ASC
        scored_items.sort(
            key=lambda x: (
                -(x["score"] if x["score"] is not None else -1.0),
                -x["protein_g"],
                x["name"],
            )
        )
    else:
        # Alphabetical sort
        scored_items.sort(key=lambda x: x["name"])

    # Deduplicate by food name (keeping first / best)
    seen_names = set()
    deduped_results: List[Dict[str, Any]] = []
    for item in scored_items:
        if item["name"] not in seen_names:
            seen_names.add(item["name"])
            deduped_results.append(item)

    return deduped_results
