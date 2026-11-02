import json
import logging
import re
from typing import Optional, Tuple
import httpx

from app.config import (
    EXTERNAL_API_KEY,
    EXTERNAL_BASE_URL,
    EXTERNAL_MODEL,
    EXTERNAL_TIMEOUT,
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


def clean_json_markdown(text: str) -> str:
    """Strips markdown code fences (```json ... ```) from model output."""
    trimmed = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", trimmed, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return trimmed


def resolve_default_base_url(model_name: str) -> str:
    """Infers the default OpenAI-compatible API base URL from the model name."""
    m = model_name.lower()
    if "deepseek" in m:
        return "https://api.deepseek.com/v1"
    if "mistral" in m:
        return "https://api.mistral.ai/v1"
    if "groq" in m:
        return "https://api.groq.com/openai/v1"
    if "openrouter" in m or "/" in m:
        return "https://openrouter.ai/api/v1"
    return "https://api.openai.com/v1"


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
            clean_content = clean_json_markdown(raw_content)
            prefs = Preferences.model_validate_json(clean_content)
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
    Calls Google Gemini API via official google-genai SDK.
    """
    key = api_key or EXTERNAL_API_KEY
    if not key or key.strip() == "":
        return (
            None,
            "No API key is set for Gemini, so the text query was ignored.",
        )

    model = model_name or EXTERNAL_MODEL
    call_timeout = timeout or EXTERNAL_TIMEOUT

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
                raw_text = clean_json_markdown(response.text or "{}")
                prefs = Preferences.model_validate_json(raw_text)
                return prefs, None
            except json.JSONDecodeError as jde:
                if attempt == 0:
                    logger.warning(f"Invalid JSON from Gemini, retrying once: {jde}")
                    continue
                return (
                    None,
                    "Gemini returned an invalid response format; using the form only.",
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
                        "The text query to Gemini timed out; using the form only.",
                    )

                if attempt == 0:
                    logger.warning(f"Error calling Gemini, retrying once: {e}")
                    continue

                return (
                    None,
                    f"Gemini API error ({type(e).__name__}); using the form only.",
                )

        return (
            None,
            "The text query could not be processed by Gemini; using the form only.",
        )
    except Exception as e:
        logger.error(f"Failed to initialize or call Gemini client: {e}")
        return (
            None,
            f"Failed to call Gemini ({type(e).__name__}); using the form only.",
        )


def extract_preferences_from_openai_compatible(
    query: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Calls any OpenAI-compatible API (OpenAI, Groq, DeepSeek, Mistral, OpenRouter, etc.).
    """
    key = api_key or EXTERNAL_API_KEY
    model = model_name or EXTERNAL_MODEL
    b_url = (base_url or EXTERNAL_BASE_URL or resolve_default_base_url(model)).rstrip("/")
    call_timeout = timeout or EXTERNAL_TIMEOUT

    if not key or key.strip() == "":
        return (
            None,
            f"No API key is set for external LLM ('{model}'), so the text query was ignored.",
        )

    endpoint = f"{b_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(2):
        try:
            with httpx.Client(timeout=call_timeout) as client:
                resp = client.post(endpoint, headers=headers, json=payload)

            # If provider doesn't support response_format: {"type": "json_object"}
            if resp.status_code == 400 and "response_format" in resp.text:
                payload.pop("response_format", None)
                with httpx.Client(timeout=call_timeout) as client:
                    resp = client.post(endpoint, headers=headers, json=payload)

            if resp.status_code in (401, 403):
                return (
                    None,
                    f"External LLM API key unauthorized (HTTP {resp.status_code}); using form only.",
                )
            if resp.status_code == 429:
                return (
                    None,
                    "External LLM API quota or rate limit exceeded; using form only.",
                )

            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
            clean_content = clean_json_markdown(raw_content)
            prefs = Preferences.model_validate_json(clean_content)
            return prefs, None

        except json.JSONDecodeError as jde:
            if attempt == 0:
                logger.warning(f"Invalid JSON from external LLM ({model}), retrying once: {jde}")
                continue
            return (
                None,
                f"External LLM ({model}) returned invalid JSON format; using form only.",
            )
        except httpx.ConnectError:
            return (
                None,
                f"Could not connect to external LLM at {b_url}. Check network connection.",
            )
        except httpx.TimeoutException:
            return (
                None,
                f"External LLM ({model}) request timed out; using form only.",
            )
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Error calling external LLM ({model}), retrying once: {e}")
                continue
            return (
                None,
                f"External LLM error ({type(e).__name__}); using form only.",
            )

    return (
        None,
        f"The text query could not be processed by external LLM ({model}); using form only.",
    )


def extract_preferences_from_external(
    query: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Routes external query either to native Gemini or OpenAI-compatible endpoint.
    """
    key = api_key or EXTERNAL_API_KEY
    model = model_name or EXTERNAL_MODEL
    custom_base_url = base_url or EXTERNAL_BASE_URL

    # If an explicit custom base_url is provided, use OpenAI-compatible chat completions
    if custom_base_url:
        return extract_preferences_from_openai_compatible(
            query=query,
            api_key=key,
            model_name=model,
            base_url=custom_base_url,
            timeout=timeout,
        )

    # If model is Gemini without a custom base_url, use official Gemini SDK
    if model.lower().startswith("gemini") or key.startswith("AIza"):
        return extract_preferences_from_gemini(
            query=query,
            api_key=key,
            model_name=model,
            timeout=timeout,
        )

    # Any other external model (OpenAI, Groq, DeepSeek, Mistral, OpenRouter, etc.)
    return extract_preferences_from_openai_compatible(
        query=query,
        api_key=key,
        model_name=model,
        base_url=resolve_default_base_url(model),
        timeout=timeout,
    )


def extract_preferences_from_query(
    query: str,
    use_local_llm: Optional[bool] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Preferences], Optional[str]]:
    """
    Main entrypoint:
    Extracts preferences using local Ollama if USE_LOCAL_LLM is True,
    otherwise uses the configured external LLM (Gemini, OpenAI, Groq, DeepSeek, etc.).
    """
    use_local = USE_LOCAL_LLM if use_local_llm is None else use_local_llm
    if use_local:
        return extract_preferences_from_ollama(
            query=query,
            base_url=base_url,
            model_name=model_name,
            timeout=timeout,
        )
    else:
        return extract_preferences_from_external(
            query=query,
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
            timeout=timeout,
        )
