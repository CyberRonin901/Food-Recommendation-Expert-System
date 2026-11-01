import os
from unittest.mock import MagicMock, patch
import pytest

from app.llm import extract_preferences_from_query
from app.schemas import Preferences


def test_missing_gemini_key():
    prefs, warn = extract_preferences_from_query("high protein dinner", api_key="")
    assert prefs is None
    assert "No Gemini API key is set" in warn


@patch("google.genai.Client")
def test_valid_gemini_response(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = '{"meal_type": "Dinner", "goals": ["high_protein"], "max_calories": 500, "exclude_keywords": ["chicken"]}'
    mock_client.models.generate_content.return_value = mock_response

    prefs, warn = extract_preferences_from_query(
        "high protein dinner under 500 calories, no chicken",
        api_key="mock_key",
    )
    assert warn is None
    assert prefs is not None
    assert prefs.meal_type == "Dinner"
    assert prefs.goals == ["high_protein"]
    assert prefs.max_calories == 500.0
    assert prefs.exclude_keywords == ["chicken"]


@patch("google.genai.Client")
def test_retry_on_invalid_json(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bad_resp = MagicMock()
    bad_resp.text = '{"meal_type": "Dinner", INVALID_JSON'

    good_resp = MagicMock()
    good_resp.text = '{"meal_type": "Dinner", "min_protein": 25}'

    mock_client.models.generate_content.side_effect = [bad_resp, good_resp]

    prefs, warn = extract_preferences_from_query("dinner with 25g protein", api_key="mock_key")
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

    prefs, warn = extract_preferences_from_query("anything", api_key="mock_key")
    assert prefs is None
    assert "quota or rate limit" in warn
    assert mock_client.models.generate_content.call_count == 1


@patch("google.genai.Client")
def test_timeout_error(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.models.generate_content.side_effect = Exception("Deadline Exceeded / timeout")

    prefs, warn = extract_preferences_from_query("anything", api_key="mock_key")
    assert prefs is None
    assert "timed out" in warn


@patch("google.genai.Client")
def test_auth_error(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.models.generate_content.side_effect = Exception("401 PERMISSION_DENIED: API_KEY_INVALID")

    prefs, warn = extract_preferences_from_query("anything", api_key="mock_key")
    assert prefs is None
    assert "invalid or unauthorized" in warn
