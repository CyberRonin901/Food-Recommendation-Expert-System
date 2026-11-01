import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    DB_PATH,
    FRONTEND_DIR,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OLLAMA_MODEL,
    USE_LOCAL_LLM,
)
from app.db import get_connection, get_db
from app.pipeline import recommend
from app.schemas import (
    HealthResponse,
    NutrientRange,
    OptionsResponse,
    RecommendRequest,
    RecommendResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify DB exists on startup
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database at {DB_PATH} not found. Run build_database.py first.")
    yield


app = FastAPI(
    title="Nutrition-Based Food Recommender API",
    description="Rule-based filtering, soft goal-based ranking, and Gemini-powered query interpretation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Optional CORS middleware for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health_check(conn: sqlite3.Connection = Depends(get_db)):
    food_count = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM foods")
        food_count = cur.fetchone()[0]
    except Exception as e:
        print(f"Health check DB error: {e}")
        food_count = 0

    if USE_LOCAL_LLM:
        llm_configured = bool(OLLAMA_MODEL and OLLAMA_MODEL.strip())
        provider = "ollama"
        model = OLLAMA_MODEL
    else:
        llm_configured = bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())
        provider = "gemini"
        model = GEMINI_MODEL

    return HealthResponse(
        status="ok",
        foods=food_count,
        llm_configured=llm_configured,
        llm_provider=provider,
        llm_model=model,
    )


@app.get("/api/options", response_model=OptionsResponse)
def get_options(conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.cursor()

    # Meal types
    cur.execute("SELECT DISTINCT meal_type FROM foods WHERE meal_type != 'Side' ORDER BY meal_type")
    meal_types = [row[0] for row in cur.fetchall()]

    # Main categories
    cur.execute("SELECT DISTINCT category_main FROM foods ORDER BY category_main")
    categories = [row[0] for row in cur.fetchall()]

    # Goals
    goals = [
        {"id": "high_protein", "label": "High Protein"},
        {"id": "high_fiber", "label": "High Fiber"},
        {"id": "low_carbs", "label": "Low Carbs"},
        {"id": "low_fat", "label": "Low Fat"},
        {"id": "low_sugar", "label": "Low Sugar"},
        {"id": "low_sodium", "label": "Low Sodium"},
        {"id": "low_cholesterol", "label": "Low Cholesterol"},
    ]

    # Nutrient ranges
    cur.execute(
        """
        SELECT
            min(calories), max(calories),
            min(protein_g), max(protein_g),
            min(carbs_g), max(carbs_g),
            min(fat_g), max(fat_g),
            min(fiber_g), max(fiber_g),
            min(sugars_g), max(sugars_g),
            min(sodium_mg), max(sodium_mg),
            min(cholesterol_mg), max(cholesterol_mg)
        FROM foods
        """
    )
    row = cur.fetchone()
    nutrient_ranges: Dict[str, NutrientRange] = {}
    if row:
        nutrients = [
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
            "sugars_g",
            "sodium_mg",
            "cholesterol_mg",
        ]
        for i, nut in enumerate(nutrients):
            nutrient_ranges[nut] = NutrientRange(
                min=float(row[i * 2] if row[i * 2] is not None else 0),
                max=float(row[i * 2 + 1] if row[i * 2 + 1] is not None else 0),
            )

    return OptionsResponse(
        meal_types=meal_types,
        categories=categories,
        goals=goals,
        nutrient_ranges=nutrient_ranges,
    )


@app.post("/api/recommend", response_model=RecommendResponse)
def post_recommend(
    request: RecommendRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return recommend(request, conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve frontend static assets if the directory exists
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

