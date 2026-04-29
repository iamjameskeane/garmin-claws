import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from garmin_claws.cli import app

runner = CliRunner()

pytestmark = pytest.mark.integration

EXPECTED_ENVELOPE_KEYS = {"ok", "schema_version", "data", "warnings", "meta"}


def parse_json(result):
    return json.loads(result.stdout)


def assert_envelope(payload, expected_schema):
    missing = EXPECTED_ENVELOPE_KEYS - set(payload.keys())
    assert not missing, f"Envelope missing keys: {missing}"
    assert payload["ok"] is True
    assert payload["schema_version"] == f"garmin-claws.v1.{expected_schema}"
    assert isinstance(payload["data"], dict)
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["meta"], dict)


@pytest.fixture(autouse=True, scope="session")
def require_token_dir():
    token_dir = os.environ.get("GARMIN_CLAWS_TOKEN_DIR")
    if not token_dir:
        pytest.skip("GARMIN_CLAWS_TOKEN_DIR not set; skipping integration tests")
    token_path = Path(token_dir) / "garmin_tokens.json"
    if not token_path.exists():
        pytest.fail(f"Token file not found: {token_path}")


def test_auth_status_with_live_tokens():
    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "auth_status")
    assert payload["data"]["authenticated"] is True
    assert "token_file" in payload["data"]


def test_daily_summary_live():
    result = runner.invoke(app, ["daily", "summary", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "daily_summary")
    assert "date" in payload["data"]
    assert "metrics" in payload["data"]
    for key in ("steps", "resting_heart_rate", "body_battery", "stress_avg"):
        assert key in payload["data"]["metrics"]


def test_sleep_summary_live():
    result = runner.invoke(app, ["sleep", "summary", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "sleep_summary")
    assert "date" in payload["data"]
    assert "metrics" in payload["data"]
    for key in ("sleep_seconds", "deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds", "sleep_score"):
        assert key in payload["data"]["metrics"]


def test_activity_recent_live():
    result = runner.invoke(app, ["activity", "recent", "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "activity_list")
    assert isinstance(payload["data"]["activities"], list)


def test_health_status_live():
    result = runner.invoke(app, ["health", "status", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "health_status")
    assert payload["data"]["overall"] in ("all_in_range", "out_of_range", "insufficient_data")
    assert "metrics" in payload["data"]


def test_sleep_recovery_live():
    result = runner.invoke(app, ["sleep", "recovery", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "sleep_recovery")
    assert payload["data"]["sleep_recovery"] in ("good", "fair", "poor")
    assert payload["data"]["training_impact"] in (
        "supports_training",
        "supports_easy_or_moderate_training",
        "reduce_intensity",
    )


def test_training_load_balance_live():
    result = runner.invoke(app, ["training", "load-balance", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "training_load_balance")
    assert payload["data"]["diagnosis"] in (
        "balanced",
        "high_aerobic_shortage",
        "low_aerobic_shortage",
        "anaerobic_shortage",
        "insufficient_data",
    )
    assert "categories" in payload["data"]
    for cat in ("low_aerobic", "high_aerobic", "anaerobic"):
        assert cat in payload["data"]["categories"]


def test_training_readiness_live():
    result = runner.invoke(app, ["training", "readiness", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "training_readiness")
    assert "score" in payload["data"]
    score = payload["data"]["score"]
    assert score is None or isinstance(score, (int, float))


def test_trainability_flow_live():
    result = runner.invoke(app, ["flow", "run", "trainability", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "trainability")
    assert payload["data"]["trainability"] in ("blue", "green", "yellow", "red", "unknown")
    assert payload["data"]["max_recommended_intensity"] in (
        "hard",
        "intervals",
        "tempo",
        "moderate",
        "easy",
        "recovery_only",
    )
    assert isinstance(payload["data"]["reasoning"], list)
    assert isinstance(payload["data"]["cautions"], list)


def test_daily_coach_flow_live():
    result = runner.invoke(app, ["flow", "run", "daily-coach", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert_envelope(payload, "daily_coach")
    assert "headline" in payload["data"]
    assert "recommendation" in payload["data"]
    assert "intensity" in payload["data"]["recommendation"]
    assert "health" in payload["data"]
    assert "sleep" in payload["data"]
    assert "training" in payload["data"]
    assert "daily" in payload["data"]
    assert "trainability" in payload["data"]
