from typing import Any, Callable, Dict, Tuple


def fn_bmi(weight_kg: float, height_cm: float) -> float:
    """Calculates BMI: weight / (height/100)^2, rounded to 1 decimal place."""
    if height_cm <= 0:
        return 0.0
    h_m = height_cm / 100.0
    return round(float(weight_kg) / (h_m * h_m), 1)


def fn_bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: float) -> float:
    """
    Mifflin-St Jeor BMR formula (adults):
    Male:   10 * w + 6.25 * h - 5 * age + 5
    Female: 10 * w + 6.25 * h - 5 * age - 161
    """
    w = float(weight_kg)
    h = float(height_cm)
    a = float(age)
    base = 10.0 * w + 6.25 * h - 5.0 * a
    if str(sex).lower() == "male":
        return round(base + 5.0, 2)
    else:
        return round(base - 161.0, 2)


def fn_product(a: float, b: float) -> float:
    """Computes a * b rounded to 1 decimal."""
    return round(float(a) * float(b), 1)


def fn_daily_calories(tdee: float, adjustment: float, sex: str) -> Tuple[float, bool]:
    """
    Daily calories target with safety floor:
    Floor is 1500 kcal for males, 1200 kcal for females.
    Returns (calories, floor_applied).
    """
    raw = float(tdee) + float(adjustment)
    floor = 1500.0 if str(sex).lower() == "male" else 1200.0
    if raw < floor:
        return floor, True
    return round(raw, 1), False


WHITELISTED_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "bmi": fn_bmi,
    "bmr_mifflin": fn_bmr_mifflin,
    "product": fn_product,
    "daily_calories": fn_daily_calories,
}

