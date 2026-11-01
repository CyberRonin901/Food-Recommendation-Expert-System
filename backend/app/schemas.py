from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

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


class HealthResponse(BaseModel):
    status: str
    foods: int
    llm_configured: bool


class NutrientRange(BaseModel):
    min: float
    max: float


class OptionsResponse(BaseModel):
    meal_types: List[str]
    categories: List[str]
    goals: List[Dict[str, str]]
    nutrient_ranges: Dict[str, NutrientRange]
