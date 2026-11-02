from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

# Section 6.1 Fact Vocabulary
VALID_FACT_NAMESPACES = {"user", "derived", "constraint", "food"}

VALID_FACT_PREFIXES = (
    "user.",
    "derived.",
    "constraint.",
    "food.",
)

ALLOWED_FACTS = {
    # user.*
    "user.goal",
    "user.meal_type",
    "user.conditions",
    "user.diet",
    "user.want_calorie_target",
    "user.age",
    "user.sex",
    "user.height_cm",
    "user.weight_kg",
    "user.activity_level",
    # derived.*
    "derived.bmi",
    "derived.bmi_category",
    "derived.bmr",
    "derived.activity_factor",
    "derived.calorie_adjustment",
    "derived.tdee",
    "derived.daily_calories",
    "derived.floor_applied",
    "derived.meal_share",
    "derived.meal_calorie_budget",
    "derived.suggested_focus",
    # constraint.*
    "constraint.max_calories",
    "constraint.min_calories",
    "constraint.min_protein",
    "constraint.max_carbs",
    "constraint.max_fat",
    "constraint.min_fiber",
    "constraint.max_sugars",
    "constraint.max_sodium",
    "constraint.max_cholesterol",
    "constraint.goals",
    "constraint.exclude_keywords",
    "constraint.warnings",
    # food.*
    "food.calories",
    "food.protein_g",
    "food.carbs_g",
    "food.fat_g",
    "food.fiber_g",
    "food.sugars_g",
    "food.sodium_mg",
    "food.cholesterol_mg",
    "food.category_main",
    "food.meal_type",
    "food.tags",
}


class RuleAction(BaseModel):
    set: Optional[Dict[str, Any]] = None
    compute: Optional[Dict[str, Any]] = None
    tighten_max: Optional[Dict[str, Any]] = None
    tighten_min: Optional[Dict[str, Any]] = None
    add_goal: Optional[str] = None
    add_exclude: Optional[List[str]] = None
    warn: Optional[str] = None
    tag: Optional[str] = None
    score: Optional[Dict[str, Any]] = None


class Rule(BaseModel):
    id: str
    name: str
    priority: int = 0
    condition: Union[str, Dict[str, Any]] = Field(alias="if")
    then: List[Dict[str, Any]]
    layer: Optional[str] = None
    basis: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None

    class Config:
        populate_by_name = True


class Question(BaseModel):
    id: str
    fact: str
    text: str
    type: Literal["single", "multi", "boolean", "number"]
    options: Optional[List[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    ask_if: Optional[Dict[str, Any]] = None
    required: bool = False
    why: str
    note: Optional[str] = None

