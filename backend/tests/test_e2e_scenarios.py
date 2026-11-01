from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_scenario_1_dinner_high_protein():
    res = client.post("/api/recommend", json={
        "meal_type": "Dinner",
        "max_calories": 500,
        "min_protein": 25,
        "include_condiments": False,
        "top_k": 20,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 15
    names = [r["name"] for r in data["results"]]
    assert any("Beef Steak (6oz sirloin)" in name for name in names)
    steak = next(r for r in data["results"] if "Beef Steak (6oz sirloin)" in r["name"])
    assert steak["protein_g"] == 42.0


def test_scenario_2_low_sodium_high_fiber():
    res = client.post("/api/recommend", json={
        "max_sodium": 140,
        "min_fiber": 5,
        "include_condiments": False,
        "top_k": 20,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 15
    names = [r["name"] for r in data["results"]]
    assert any("Raspberries (1 cup)" in name for name in names)
    assert any("Black Beans (1/2 cup)" in name for name in names)


def test_scenario_3_breakfast_categories():
    res = client.post("/api/recommend", json={
        "meal_type": "Breakfast",
        "max_sugars": 10,
        "max_calories": 300,
        "categories": ["Grain", "Dairy", "Fruit", "Protein", "Nut"],
        "top_k": 50,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 31


def test_scenario_4_min_protein_60():
    res = client.post("/api/recommend", json={"min_protein": 60})
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 0
    assert len(data["results"]) == 0
    assert any("Try relaxing: min_protein (60)" in w for w in data["warnings"])


def test_scenario_5_impossible_calories_protein():
    res = client.post("/api/recommend", json={"max_calories": 50, "min_protein": 20})
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 0
    assert len(data["results"]) == 0


def test_scenario_6_min_greater_than_max():
    res = client.post("/api/recommend", json={"min_calories": 400, "max_calories": 200})
    assert res.status_code == 422


def test_scenario_7_exclude_keywords_ham():
    res = client.post("/api/recommend", json={"exclude_keywords": ["ham"], "top_k": 50})
    assert res.status_code == 200
    data = res.json()
    for r in data["results"]:
        words = r["name"].lower().split()
        assert "ham" not in words

    # Verify Bun (hamburger) is not wrongly removed
    res_bun = client.post("/api/recommend", json={
        "categories": ["Grain"],
        "include_keywords": ["hamburger"],
        "exclude_keywords": ["ham"],
    })
    assert res_bun.status_code == 200
    names = [r["name"] for r in res_bun.json()["results"]]
    assert any("Bun (hamburger)" in name for name in names)


def test_scenario_8_goals_high_protein():
    res = client.post("/api/recommend", json={"goals": ["high_protein"], "top_k": 20})
    assert res.status_code == 200
    proteins = [r["protein_g"] for r in res.json()["results"]]
    assert proteins == sorted(proteins, reverse=True)


def test_scenario_9_no_goals():
    res = client.post("/api/recommend", json={"meal_type": "Breakfast", "top_k": 10})
    assert res.status_code == 200
    data = res.json()
    for r in data["results"]:
        assert r["score"] is None
    names = [r["name"] for r in data["results"]]
    assert names == sorted(names)
    assert any("alphabetically" in w for w in data["warnings"])


def test_scenario_10_deduplicate_names():
    res = client.post("/api/recommend", json={"include_keywords": ["salami"], "top_k": 10})
    assert res.status_code == 200
    matches = [r for r in res.json()["results"] if "Salami (3 slices)" in r["name"]]
    assert len(matches) <= 1
