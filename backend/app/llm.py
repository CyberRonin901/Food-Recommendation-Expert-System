import json
import logging
from typing import Optional, Tuple
import httpx

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TIMEOUT,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    USE_LOCAL_LLM,
)
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


def extract_preferences_from_ollama(
    query: str,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Calls local Ollama chat API with JSON schema constraint.
    Returns (Preferences, warning_message).
    """
    url = f"{(base_url or OLLAMA_BASE_URL).rstrip('/')}/api/chat"
    model = model_name or OLLAMA_MODEL
    req_timeout = timeout or OLLAMA_TIMEOUT

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "format": Preferences.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0.0},
    }

    for attempt in range(2):
        try:
            with httpx.Client(timeout=req_timeout) as client:
                resp = client.post(url, json=payload)

            if resp.status_code == 404:
                return (
                    None,
                    f"Ollama model '{model}' not found on host. Run `ollama pull {model}`.",
                )

            resp.raise_for_status()
            data = resp.json()
            raw_content = data.get("message", {}).get("content", "{}")
            prefs = Preferences.model_validate_json(raw_content)
            return prefs, None

        except json.JSONDecodeError as jde:
            if attempt == 0:
                logger.warning(f"Invalid JSON from Ollama, retrying once: {jde}")
                continue
            return (
                None,
                "Ollama returned an invalid response format; using the form only.",
            )
        except httpx.ConnectError:
            target_url = base_url or OLLAMA_BASE_URL
            return (
                None,
                f"Could not connect to Ollama at {target_url}. Make sure Ollama is running (`ollama serve`).",
            )
        except httpx.TimeoutException:
            return (
                None,
                f"Local Ollama request timed out after {req_timeout}s; using the form only.",
            )
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Error calling Ollama, retrying once: {e}")
                continue
            return (
                None,
                f"Ollama request error ({type(e).__name__}); using the form only.",
            )

    return (
        None,
        "The text query could not be processed by Ollama; using the form only.",
    )


def extract_preferences_from_gemini(
    query: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Calls Gemini API to parse natural language text into a structured Preferences object.
    Returns (Preferences, warning_message).
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


def extract_preferences_from_query(
    query: str,
    use_local_llm: Optional[bool] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Extracts preferences using local Ollama if USE_LOCAL_LLM is True,
    otherwise uses Gemini API.
    """
    use_local = USE_LOCAL_LLM if use_local_llm is None else use_local_llm
    if use_local:
        return extract_preferences_from_ollama(
            query=query,
            model_name=model_name,
            timeout=timeout,
        )
    else:
        return extract_preferences_from_gemini(
            query=query,
            api_key=api_key,
            model_name=model_name,
            timeout=timeout,
        )
