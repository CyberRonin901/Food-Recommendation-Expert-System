from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from app.expert.schemas import Question

# The expert module defines a Question schema used by the wizard.
# It is imported here so that `app.main` can reference `app.schemas.Question`.
# This avoids circular imports and keeps a single source of truth.


MealTypeLiteral = Literal["Breakfast", "Lunch", "Dinner", "Snack"]

CategoryLiteral = Literal[
    "Condiment",
    "Meal",
    "Vegetable",
    "Grain",
    "Beverage",
    "Protein",
    "Fruit",
    "Dairy",
    "Dessert",
    "Snack",
    "Nut",
    "Legume",
    "Supplement",
]

GoalLiteral = Literal[
    "high_protein",
    "high_fiber",
    "low_carbs",
    "low_fat",
    "low_sugar",
    "low_sodium",
    "low_cholesterol",
]

UserGoalLiteral = Literal[
    "weight_loss",
    "weight_gain",
    "muscle_gain",
    "maintain",
    "heart_health",
    "blood_sugar_control",
]

ConditionLiteral = Literal[
    "hypertension",
    "type2_diabetes",
    "high_cholesterol",
]

DietLiteral = Literal[
    "vegetarian",
    "vegan",
    "no_beef",
    "no_pork",
]

ActivityLevelLiteral = Literal[
    "sedentary",
    "light",
    "moderate",
    "very_active",
]


class UserProfile(BaseModel):
    goal: Optional[UserGoalLiteral] = None
    meal_type: Optional[MealTypeLiteral] = None
    conditions: Optional[List[ConditionLiteral]] = Field(default_factory=list)
    diet: Optional[List[DietLiteral]] = Field(default_factory=list)
    want_calorie_target: Optional[bool] = None
    age: Optional[float] = Field(default=None, ge=10, le=100)
    sex: Optional[Literal["male", "female"]] = None
    height_cm: Optional[float] = Field(default=None, ge=100, le=230)
    weight_kg: Optional[float] = Field(default=None, ge=25, le=250)
    activity_level: Optional[ActivityLevelLiteral] = None


class Preferences(BaseModel):
    meal_type: Optional[MealTypeLiteral] = None
    categories: Optional[List[CategoryLiteral]] = None
    goals: Optional[List[GoalLiteral]] = None
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    include_condiments: Optional[bool] = None
    min_calories: Optional[float] = Field(default=None, ge=0)
    max_calories: Optional[float] = Field(default=None, ge=0)
    min_protein: Optional[float] = Field(default=None, ge=0)
    max_carbs: Optional[float] = Field(default=None, ge=0)
    max_fat: Optional[float] = Field(default=None, ge=0)
    min_fiber: Optional[float] = Field(default=None, ge=0)
    max_sugars: Optional[float] = Field(default=None, ge=0)
    max_sodium: Optional[float] = Field(default=None, ge=0)
    max_cholesterol: Optional[float] = Field(default=None, ge=0)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def validate_calorie_bounds(self) -> "Preferences":
        if self.min_calories is not None and self.max_calories is not None:
            if self.min_calories > self.max_calories:
                raise ValueError("min_calories cannot be greater than max_calories")
        return self


class RecommendRequest(BaseModel):
    query: Optional[str] = None
    meal_type: Optional[MealTypeLiteral] = None
    categories: Optional[List[CategoryLiteral]] = None
    goals: Optional[List[GoalLiteral]] = None
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    include_condiments: Optional[bool] = None
    min_calories: Optional[float] = Field(default=None, ge=0)
    max_calories: Optional[float] = Field(default=None, ge=0)
    min_protein: Optional[float] = Field(default=None, ge=0)
    max_carbs: Optional[float] = Field(default=None, ge=0)
    max_fat: Optional[float] = Field(default=None, ge=0)
    min_fiber: Optional[float] = Field(default=None, ge=0)
    max_sugars: Optional[float] = Field(default=None, ge=0)
    max_sodium: Optional[float] = Field(default=None, ge=0)
    max_cholesterol: Optional[float] = Field(default=None, ge=0)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def validate_calorie_bounds(self) -> "RecommendRequest":
        if self.min_calories is not None and self.max_calories is not None:
            if self.min_calories > self.max_calories:
                raise ValueError("min_calories cannot be greater than max_calories")
        return self


class FoodResult(BaseModel):
    id: int
    name: str
    category: str
    meal_type: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugars_g: float
    sodium_mg: float
    cholesterol_mg: float
    score: Optional[float] = None
    reasons: List[str] = []


class RecommendResponse(BaseModel):
    interpreted: Dict[str, Any]
    total_matches: int
    results: List[FoodResult]
    warnings: List[str] = []


class ConsultFoodResult(BaseModel):
    id: Optional[int] = None
    name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugars_g: float
    sodium_mg: float
    cholesterol_mg: float
    category: Optional[str] = None
    meal_type: Optional[str] = None
    cf: Optional[float] = None
    score: Optional[float] = None
    tags: List[str] = []
    how: List[str] = []


class ConsultRequest(BaseModel):
    facts: Optional[Dict[str, Any]] = Field(default_factory=dict)
    query: Optional[str] = None
    top_k: Optional[int] = Field(default=10, ge=1, le=50)


class ConsultResponse(BaseModel):
    constraints: Dict[str, Any]
    warnings: List[str] = []
    phase_a_trace: List[Dict[str, Any]] = []
    total_matches: int
    results: List[ConsultFoodResult]


class WhyNotRequest(BaseModel):
    food_name: str
    facts: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WhyNotResponse(BaseModel):
    food_name: str
    included: bool
    reason: str
    failing_constraint: Optional[str] = None
    violating_value: Optional[Any] = None
    threshold: Optional[Any] = None
    rule_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    foods: int
    rules_loaded: int = 85
    llm_configured: bool
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class NutrientRange(BaseModel):
    min: float
    max: float


class OptionsResponse(BaseModel):
    meal_types: List[str]
    categories: List[str]
    goals: List[Dict[str, str]]
    nutrient_ranges: Dict[str, NutrientRange]
