import sqlite3
import pytest
from pydantic import ValidationError

from app.config import DB_PATH
from app.db import get_connection
from app.pipeline import recommend
from app.schemas import RecommendRequest


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.close()


def test_scenario_dinner_high_protein(db_conn):
    # Dinner, max_calories 500, min_protein 25 -> 15 matches; Beef Steak (6oz sirloin) is among them
    req = RecommendRequest(
        meal_type="Dinner",
        max_calories=500,
        min_protein=25,
        include_condiments=False,
    )
    res = recommend(req, db_conn)
    assert res.total_matches == 15
    steak = next((r for r in res.results if "Beef Steak (6oz sirloin)" in r.name), None)
    assert steak is not None
    assert steak.protein_g == 42.0


def test_scenario_low_sodium_high_fiber(db_conn):
    # max_sodium 140, min_fiber 5 -> 15 matches; includes Raspberries and Black Beans
    req = RecommendRequest(
        max_sodium=140,
        min_fiber=5,
        include_condiments=False,
        top_k=20,
    )
    res = recommend(req, db_conn)
    assert res.total_matches == 15
    names = [r.name for r in res.results]
    assert any("Raspberries (1 cup)" in name for name in names)
    assert any("Black Beans (1/2 cup)" in name for name in names)


def test_scenario_breakfast_categories(db_conn):
    # Breakfast, max_sugars 10, max_calories 300, categories Grain/Dairy/Fruit/Protein/Nut -> 31 matches
    req = RecommendRequest(
        meal_type="Breakfast",
        max_sugars=10,
        max_calories=300,
        categories=["Grain", "Dairy", "Fruit", "Protein", "Nut"],
    )
    res = recommend(req, db_conn)
    assert res.total_matches == 31


def test_scenario_no_matches_warning(db_conn):
    # min_protein 60 -> 0 matches, results: [] with warning
    req = RecommendRequest(min_protein=60)
    res = recommend(req, db_conn)
    assert res.total_matches == 0
    assert len(res.results) == 0
    assert any("Try relaxing: min_protein (60)" in w for w in res.warnings)


def test_scenario_impossible_calories_and_protein(db_conn):
    # max_calories 50 and min_protein 20 -> 0 matches
    req = RecommendRequest(max_calories=50, min_protein=20)
    res = recommend(req, db_conn)
    assert res.total_matches == 0
    assert len(res.results) == 0


def test_min_greater_than_max_calories_rejected():
    # min_calories 400 with max_calories 200 -> validation error
    with pytest.raises(ValidationError):
        RecommendRequest(min_calories=400, max_calories=200)


def test_exclude_keywords_ham(db_conn):
    # exclude_keywords = ["ham"] -> No result has 'ham' in name, but Bun (hamburger) is NOT removed
    req = RecommendRequest(exclude_keywords=["ham"])
    res = recommend(req, db_conn)
    for r in res.results:
        # Check name_search or words
        words = r.name.lower().split()
        assert "ham" not in words, f"Found 'ham' in result {r.name}"

    # Also verify Bun (hamburger) is present if matching other criteria
    req_bun = RecommendRequest(
        categories=["Grain"],
        include_keywords=["hamburger"],
        exclude_keywords=["ham"],
    )
    res_bun = recommend(req_bun, db_conn)
    assert any("Bun (hamburger)" in r.name for r in res_bun.results)


def test_goals_high_protein_ordering(db_conn):
    # Goals: high_protein only -> Results are in descending protein order
    req = RecommendRequest(goals=["high_protein"], top_k=20)
    res = recommend(req, db_conn)
    proteins = [r.protein_g for r in res.results]
    assert proteins == sorted(proteins, reverse=True)


def test_no_goals_alphabetical_and_note(db_conn):
    # No goals -> score is null, results alphabetical, note in warnings
    req = RecommendRequest(meal_type="Breakfast", top_k=10)
    res = recommend(req, db_conn)
    for r in res.results:
        assert r.score is None
    names = [r.name for r in res.results]
    assert names == sorted(names)
    assert any("alphabetically" in w for w in res.warnings)


def test_duplicate_food_names_appear_once(db_conn):
    # Same food name in two rows (e.g. Salami (3 slices)) appears once
    req = RecommendRequest(include_keywords=["salami"])
    res = recommend(req, db_conn)
    salami_matches = [r for r in res.results if "Salami (3 slices)" in r.name]
    assert len(salami_matches) <= 1
