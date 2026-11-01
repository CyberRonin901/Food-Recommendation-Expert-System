import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["foods"] == 597
    assert "llm_configured" in data


def test_options_endpoint():
    response = client.get("/api/options")
    assert response.status_code == 200
    data = response.json()
    assert "meal_types" in data
    assert "Breakfast" in data["meal_types"]
    assert "categories" in data
    assert "Protein" in data["categories"]
    assert "goals" in data
    assert len(data["goals"]) == 7
    assert "nutrient_ranges" in data
    assert "calories" in data["nutrient_ranges"]
    assert data["nutrient_ranges"]["calories"]["max"] >= 600


def test_recommend_endpoint_success():
    payload = {
        "meal_type": "Dinner",
        "max_calories": 500,
        "min_protein": 25,
        "goals": ["high_protein"],
        "top_k": 5,
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] == 15
    assert len(data["results"]) == 5
    assert data["results"][0]["score"] is not None
    assert len(data["results"][0]["reasons"]) > 0


def test_recommend_endpoint_validation_error():
    payload = {
        "min_calories": 400,
        "max_calories": 200,
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 422


def test_frontend_static_serving():
    response = client.get("/")
    assert response.status_code == 200
    assert "Nutrition-Based Food Recommender" in response.text

    css_res = client.get("/style.css")
    assert css_res.status_code == 200
    assert "--primary" in css_res.text

    js_res = client.get("/app.js")
    assert js_res.status_code == 200
    assert "recommenderForm" in js_res.text
