import json
import logging
from typing import Optional, Tuple
from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT
from app.schemas import Preferences

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a nutrition assistant that translates a user's food request into structured search filters.
Output ONLY a valid JSON object matching the schema.
Instructions:
- Fill ONLY fields that the user actually stated or implied in the request.
- Leave everything else null / unset. NEVER guess or invent numbers or constraints.
- Allowed meal types: "Breakfast", "Lunch", "Dinner", "Snack".
- Allowed categories: "Condiment", "Meal", "Vegetable", "Grain", "Beverage", "Protein", "Fruit", "Dairy", "Dessert", "Snack", "Nut", "Legume", "Supplement".
- Allowed goals: "high_protein", "high_fiber", "low_carbs", "low_fat", "low_sugar", "low_sodium", "low_cholesterol".
- If the user specifies ingredient inclusions, put them into include_keywords (e.g. ["salmon"]).
- If the user specifies exclusions, put them into exclude_keywords (e.g. ["chicken", "pork"]).
- top_k is an integer between 1 and 50 if the user explicitly requested a count (e.g. "give me 3 breakfast ideas" -> top_k: 3).
"""


def extract_preferences_from_query(
    query: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Calls Gemini API to parse natural language text into a structured Preferences object.
    Returns (Preferences, warning_message).
    Never raises an exception — on failure, returns (None, warning).
    """
    key = api_key or GEMINI_API_KEY
    if not key or key.strip() == "":
        return (
            None,
            "No Gemini API key is set, so the text query was ignored.",
        )

    model = model_name or GEMINI_MODEL
    call_timeout = timeout or GEMINI_TIMEOUT

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=Preferences,
            http_options=types.HttpOptions(timeout=int(call_timeout * 1000)),
        )

        # First attempt
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=query,
                    config=config,
                )
                raw_text = response.text or "{}"
                prefs = Preferences.model_validate_json(raw_text)
                return prefs, None
            except json.JSONDecodeError as jde:
                if attempt == 0:
                    logger.warning(f"Invalid JSON from Gemini, retrying once: {jde}")
                    continue
                return (
                    None,
                    "The text query could not be processed (invalid response format); using the form only.",
                )
            except Exception as e:
                err_str = str(e)
                # Check for quota or auth errors - do not retry
                if "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower() or "429" in err_str:
                    return (
                        None,
                        "The text query could not be processed (quota or rate limit); using the form only.",
                    )
                if "PERMISSION_DENIED" in err_str or "API_KEY_INVALID" in err_str or "401" in err_str or "403" in err_str:
                    return (
                        None,
                        "The Gemini API key is invalid or unauthorized; using the form only.",
                    )
                if "deadline" in err_str.lower() or "timeout" in err_str.lower():
                    return (
                        None,
                        "The text query timed out; using the form only.",
                    )

                if attempt == 0:
                    logger.warning(f"Error calling Gemini, retrying once: {e}")
                    continue

                return (
                    None,
                    f"The text query could not be processed ({type(e).__name__}); using the form only.",
                )

        return (
            None,
            "The text query could not be processed; using the form only.",
        )
    except Exception as e:
        logger.error(f"Failed to initialize or call Gemini client: {e}")
        return (
            None,
            f"The text query could not be processed ({type(e).__name__}); using the form only.",
        )
