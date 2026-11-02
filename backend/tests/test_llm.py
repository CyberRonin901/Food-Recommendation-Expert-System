import os
from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.llm import (
    clean_json_markdown,
    extract_preferences_from_external,
    extract_preferences_from_gemini,
    extract_preferences_from_ollama,
    extract_preferences_from_openai_compatible,
    extract_preferences_from_query,
    resolve_default_base_url,
)
from app.schemas import Preferences


# ==============================================================================
# Helper Tests
# ==============================================================================

def test_clean_json_markdown():
    wrapped = "```json\n{\"meal_type\": \"Dinner\"}\n```"
    assert clean_json_markdown(wrapped) == "{\"meal_type\": \"Dinner\"}"

    plain = "{\"meal_type\": \"Lunch\"}"
    assert clean_json_markdown(plain) == "{\"meal_type\": \"Lunch\"}"


def test_resolve_default_base_url():
    assert "deepseek" in resolve_default_base_url("deepseek-chat")
    assert "groq" in resolve_default_base_url("groq/llama-3")
    assert "mistral" in resolve_default_base_url("mistral-small")
    assert "openrouter" in resolve_default_base_url("meta-llama/llama-3")
    assert "openai" in resolve_default_base_url("gpt-4o")


# ==============================================================================
# Gemini Tests
# ==============================================================================

def test_missing_gemini_key():
    prefs, warn = extract_preferences_from_query(
        "high protein dinner",
        use_local_llm=False,
        api_key="",
        model_name="gemini-3.8-flash",
    )
    assert prefs is None
    assert "No API key is set" in warn


@patch("google.genai.Client")
def test_valid_gemini_response(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = '{"meal_type": "Dinner", "goals": ["high_protein"], "max_calories": 500, "exclude_keywords": ["chicken"]}'
    mock_client.models.generate_content.return_value = mock_response

    prefs, warn = extract_preferences_from_query(
        "high protein dinner under 500 calories, no chicken",
        use_local_llm=False,
        api_key="mock_key",
        model_name="gemini-3.8-flash",
    )
    assert warn is None
    assert prefs is not None
    assert prefs.meal_type == "Dinner"
    assert prefs.goals == ["high_protein"]
    assert prefs.max_calories == 500.0
    assert prefs.exclude_keywords == ["chicken"]


@patch("google.genai.Client")
def test_retry_on_invalid_json_gemini(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bad_resp = MagicMock()
    bad_resp.text = '{"meal_type": "Dinner", INVALID_JSON'

    good_resp = MagicMock()
    good_resp.text = '{"meal_type": "Dinner", "min_protein": 25}'

    mock_client.models.generate_content.side_effect = [bad_resp, good_resp]

    prefs, warn = extract_preferences_from_query(
        "dinner with 25g protein",
        use_local_llm=False,
        api_key="mock_key",
        model_name="gemini-3.8-flash",
    )
    assert warn is None
    assert prefs is not None
    assert prefs.meal_type == "Dinner"
    assert prefs.min_protein == 25.0
    assert mock_client.models.generate_content.call_count == 2


@patch("google.genai.Client")
def test_quota_error_no_retry(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED Quota exceeded")

    prefs, warn = extract_preferences_from_query(
        "anything",
        use_local_llm=False,
        api_key="mock_key",
        model_name="gemini-3.8-flash",
    )
    assert prefs is None
    assert "quota or rate limit" in warn
    assert mock_client.models.generate_content.call_count == 1


@patch("google.genai.Client")
def test_timeout_error_gemini(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.models.generate_content.side_effect = Exception("Deadline Exceeded / timeout")

    prefs, warn = extract_preferences_from_query(
        "anything",
        use_local_llm=False,
        api_key="mock_key",
        model_name="gemini-3.8-flash",
    )
    assert prefs is None
    assert "timed out" in warn


@patch("google.genai.Client")
def test_auth_error_gemini(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.models.generate_content.side_effect = Exception("401 PERMISSION_DENIED: API_KEY_INVALID")

    prefs, warn = extract_preferences_from_query(
        "anything",
        use_local_llm=False,
        api_key="mock_key",
        model_name="gemini-3.8-flash",
    )
    assert prefs is None
    assert "invalid or unauthorized" in warn


# ==============================================================================
# OpenAI-Compatible External API Tests (OpenAI, Groq, DeepSeek, etc.)
# ==============================================================================

@patch("httpx.Client.post")
def test_valid_openai_compatible_response(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '```json\n{"meal_type": "Dinner", "goals": ["high_protein"], "max_calories": 600}\n```'
                }
            }
        ]
    }
    mock_post.return_value = mock_resp

    prefs, warn = extract_preferences_from_query(
        "high protein dinner under 600 calories",
        use_local_llm=False,
        api_key="sk-test-key",
        model_name="gpt-4o",
    )
    assert warn is None
    assert prefs is not None
    assert prefs.meal_type == "Dinner"
    assert prefs.goals == ["high_protein"]
    assert prefs.max_calories == 600.0


@patch("httpx.Client.post")
def test_openai_compatible_custom_base_url_groq(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"meal_type": "Breakfast", "goals": ["low_sugar"]}'
                }
            }
        ]
    }
    mock_post.return_value = mock_resp

    prefs, warn = extract_preferences_from_query(
        "low sugar breakfast",
        use_local_llm=False,
        api_key="gsk-groq-key",
        model_name="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
    )
    assert warn is None
    assert prefs is not None
    assert prefs.meal_type == "Breakfast"
    assert prefs.goals == ["low_sugar"]


@patch("httpx.Client.post")
def test_openai_compatible_auth_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_post.return_value = mock_resp

    prefs, warn = extract_preferences_from_query(
        "dinner",
        use_local_llm=False,
        api_key="bad-key",
        model_name="gpt-4o",
    )
    assert prefs is None
    assert "unauthorized" in warn


@patch("httpx.Client.post")
def test_openai_compatible_rate_limit(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_post.return_value = mock_resp

    prefs, warn = extract_preferences_from_query(
        "dinner",
        use_local_llm=False,
        api_key="sk-test",
        model_name="gpt-4o",
    )
    assert prefs is None
    assert "rate limit" in warn


# ==============================================================================
# Ollama Tests
# ==============================================================================

@patch("httpx.Client.post")
def test_valid_ollama_response(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "content": '{"meal_type": "Lunch", "goals": ["low_carbs"], "max_calories": 400}'
        }
    }
    mock_post.return_value = mock_resp

    prefs, warn = extract_preferences_from_query(
        "low carb lunch under 400 calories",
        use_local_llm=True,
        model_name="llama3.2",
    )
    assert warn is None
    assert prefs is not None
    assert prefs.meal_type == "Lunch"
    assert prefs.goals == ["low_carbs"]
    assert prefs.max_calories == 400.0


@patch("httpx.Client.post")
def test_ollama_connect_error(mock_post):
    mock_post.side_effect = httpx.ConnectError("Connection refused")

    prefs, warn = extract_preferences_from_query(
        "dinner",
        use_local_llm=True,
    )
    assert prefs is None
    assert "Could not connect to Ollama" in warn


@patch("httpx.Client.post")
def test_ollama_model_not_found(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_post.return_value = mock_resp

    prefs, warn = extract_preferences_from_query(
        "dinner",
        use_local_llm=True,
        model_name="nonexistent-model",
    )
    assert prefs is None
    assert "Ollama model 'nonexistent-model' not found" in warn


@patch("httpx.Client.post")
def test_ollama_timeout(mock_post):
    mock_post.side_effect = httpx.TimeoutException("Timed out")

    prefs, warn = extract_preferences_from_query(
        "dinner",
        use_local_llm=True,
    )
    assert prefs is None
    assert "timed out" in warn
