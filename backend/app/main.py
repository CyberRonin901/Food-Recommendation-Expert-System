import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Dict, List
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    DB_PATH,
    EXTERNAL_API_KEY,
    EXTERNAL_MODEL,
    FRONTEND_DIR,
    OLLAMA_MODEL,
    USE_LOCAL_LLM,
)
from app.db import get_connection, get_db
from app.expert.consult import consult
from app.expert.engine import run_forward_chaining
from app.expert.explain import explain_why_not
from app.expert.knowledge_base import get_knowledge_base
from app.expert.memory import WorkingMemory
from app.pipeline import recommend
from app.schemas import (
    ConsultRequest,
    ConsultResponse,
    HealthResponse,
    NutrientRange,
    OptionsResponse,
    Question,
    RecommendRequest,
    RecommendResponse,
    WhyNotRequest,
    WhyNotResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database at {DB_PATH} not found. Run build_database.py first.")
    # Eagerly load knowledge base and verify rules on startup
    kb = get_knowledge_base()
    print(f"Expert system initialized: {len(kb.rules)} rules, {len(kb.questions)} questions loaded.")
    yield


app = FastAPI(
    title="Food Recommendation Expert System API",
    description="Forward-chaining rule engine, certainty factors, working memory, and explanation facility.",
    version="2.0.0",
    lifespan=lifespan,
)

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

    kb = get_knowledge_base()
    rules_count = len(kb.rules)

    if USE_LOCAL_LLM:
        llm_configured = bool(OLLAMA_MODEL and OLLAMA_MODEL.strip())
        provider = "ollama"
        model = OLLAMA_MODEL
    else:
        llm_configured = bool(EXTERNAL_API_KEY and EXTERNAL_API_KEY.strip())
        provider = "external"
        model = EXTERNAL_MODEL

    return HealthResponse(
        status="ok",
        foods=food_count,
        rules_loaded=rules_count,
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


# ==============================================================================
# Expert System Endpoints
# ==============================================================================

@app.get("/api/questions", response_model=List[Dict[str, Any]])
def get_questions():
    """Returns consultation wizard questions from questions.yaml with 'why' and 'ask_if'."""
    kb = get_knowledge_base()
    return [q.model_dump() for q in kb.questions]


@app.get("/api/rules", response_model=List[Dict[str, Any]])
def get_rules():
    """Returns metadata for all rules in the knowledge base."""
    kb = get_knowledge_base()
    return [
        {
            "id": r.id,
            "layer": r.layer,
            "name": r.name,
            "basis": r.basis,
            "source": r.source,
            "priority": r.priority,
            "note": r.note,
        }
        for r in kb.rules
    ]


@app.get("/api/rules/{rule_id}", response_model=Dict[str, Any])
def get_rule_by_id(rule_id: str):
    """Returns full details of a specific rule."""
    kb = get_knowledge_base()
    r = kb.rules_by_id.get(rule_id)
    if not r:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    return r.model_dump(by_alias=True)


@app.post("/api/consult", response_model=ConsultResponse)
def post_consult(
    request: ConsultRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Main expert system endpoint: user facts -> forward-chaining -> constraints -> CF ranking."""
    try:
        return consult(request, conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/why-not", response_model=WhyNotResponse)
def post_why_not(
    request: WhyNotRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Explains why a given food was not included in the consultation recommendations."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM foods WHERE name LIKE ? LIMIT 1", (f"%{request.food_name}%",))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Food item '{request.food_name}' not found in dataset.")

    food_dict = dict(row)

    # Re-run Phase A to obtain constraints and trace
    kb = get_knowledge_base()
    norm_facts = {}
    for k, v in request.facts.items():
        if k in ("goal", "meal_type", "conditions", "diet", "want_calorie_target", "age", "sex", "height_cm", "weight_kg", "activity_level"):
            norm_facts[f"user.{k}"] = v
        else:
            norm_facts[k] = v

    memory = WorkingMemory(initial_facts=norm_facts)
    phase_a_trace = run_forward_chaining(kb.get_phase_a_rules(), memory)

    res = explain_why_not(food_dict, memory.constraints, phase_a_trace)
    return WhyNotResponse(**res)


# ==============================================================================
# Legacy / Manual Mode Endpoint
# ==============================================================================

@app.post("/api/recommend", response_model=RecommendResponse)
def post_recommend(
    request: RecommendRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Manual/advanced mode endpoint with direct filter control."""
    try:
        return recommend(request, conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
