import re
import unicodedata
from typing import Any, List, Tuple
from app.schemas import Preferences


def normalize_keyword(word: str) -> str:
    """Normalize a keyword to match the structure of name_search."""
    nfkd = unicodedata.normalize("NFKD", word)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8").lower()
    clean = re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()
    return clean


def build_filter_query(prefs: Preferences) -> Tuple[str, List[Any]]:
    """
    Builds the SQL WHERE clause and parameters from a Preferences object.
    Returns (where_clause_sql, params).
    If no filters apply, where_clause_sql is empty string.
    """
    clauses: List[str] = []
    params: List[Any] = []

    # 1. Meal type
    if prefs.meal_type:
        clauses.append("meal_type = ?")
        params.append(prefs.meal_type)

    # 2. Categories
    if prefs.categories:
        placeholders = ", ".join(["?"] * len(prefs.categories))
        clauses.append(f"category_main IN ({placeholders})")
        params.extend(prefs.categories)

    # 3. Condiments: excluded by default unless include_condiments is True or Condiment is selected in categories
    if not prefs.include_condiments and (not prefs.categories or "Condiment" not in prefs.categories):
        clauses.append("category_main != ?")
        params.append("Condiment")

    # 4. Include keywords: name must contain at least one of the words
    if prefs.include_keywords:
        valid_words = [normalize_keyword(w) for w in prefs.include_keywords if normalize_keyword(w)]
        if valid_words:
            sub_clauses = ["name_search LIKE ?" for _ in valid_words]
            clauses.append(f"({' OR '.join(sub_clauses)})")
            for w in valid_words:
                params.append(f"% {w} %")

    # 5. Exclude keywords: name must contain none of the words
    if prefs.exclude_keywords:
        valid_words = [normalize_keyword(w) for w in prefs.exclude_keywords if normalize_keyword(w)]
        for w in valid_words:
            clauses.append("name_search NOT LIKE ?")
            params.append(f"% {w} %")

    # 6. Nutrient limits
    limits = [
        ("min_calories", "calories >= ?"),
        ("max_calories", "calories <= ?"),
        ("min_protein", "protein_g >= ?"),
        ("max_carbs", "carbs_g <= ?"),
        ("max_fat", "fat_g <= ?"),
        ("min_fiber", "fiber_g >= ?"),
        ("max_sugars", "sugars_g <= ?"),
        ("max_sodium", "sodium_mg <= ?"),
        ("max_cholesterol", "cholesterol_mg <= ?"),
    ]

    for field_name, sql_cond in limits:
        val = getattr(prefs, field_name, None)
        if val is not None:
            clauses.append(sql_cond)
            params.append(float(val))

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    return where_sql, params
