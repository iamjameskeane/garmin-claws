import json

from typer.testing import CliRunner

from garmin_claws.cli import app


runner = CliRunner()


def parse_json(result):
    return json.loads(result.stdout)


def test_cli_help_mentions_agent_friendly_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Agent-ready Garmin Connect CLI" in result.stdout
    assert "auth" in result.stdout
    assert "daily" in result.stdout
    assert "activity" in result.stdout
    assert "capabilities" in result.stdout


def test_auth_status_reports_missing_tokens_human(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CLAWS_TOKEN_DIR", str(tmp_path / "missing"))

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 2
    assert "not found" in result.stderr
    assert "garmin-claws auth login" in result.stderr


def test_auth_status_reports_missing_tokens_as_structured_json(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CLAWS_TOKEN_DIR", str(tmp_path / "missing"))

    result = runner.invoke(app, ["--agent", "auth", "status"])

    assert result.exit_code == 2
    payload = parse_json(result)
    assert payload == {
        "ok": False,
        "schema_version": "garmin-claws.v1.error",
        "error": {
            "code": "GARMIN_AUTH_MISSING",
            "message": f"Garmin token file not found: {tmp_path / 'missing' / 'garmin_tokens.json'}",
            "remediation": "Run `garmin-claws auth login --print-instructions`, then `garmin-claws auth import <zip>`.",
        },
        "warnings": [],
        "meta": {},
    }
    assert result.stderr == ""


def test_auth_login_prints_local_machine_instructions(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CLAWS_TOKEN_DIR", str(tmp_path / ".garminconnect"))

    result = runner.invoke(app, ["auth", "login", "--print-instructions"])

    assert result.exit_code == 0
    assert "Run this on your local machine" in result.stdout
    assert "garminconnect" in result.stdout
    assert "garmin-claws auth import" in result.stdout


def test_flow_plan_returns_agent_envelope_json_without_live_garmin():
    result = runner.invoke(app, ["flow", "plan", "daily-brief", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["ok"] is True
    assert payload["schema_version"] == "garmin-claws.v1.flow_plan"
    assert payload["data"]["flow"] == "daily-brief"
    assert "garmin-claws daily summary --date today --json" in payload["data"]["commands"]


def test_capabilities_lists_agent_safe_commands_as_json():
    result = runner.invoke(app, ["capabilities", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["ok"] is True
    assert payload["schema_version"] == "garmin-claws.v1.capabilities"
    command_names = {cmd["name"] for cmd in payload["data"]["commands"]}
    assert {"daily summary", "sleep summary", "activity recent", "flow plan", "schema show"}.issubset(command_names)
    assert all("requires_auth" in cmd for cmd in payload["data"]["commands"])


def test_schema_show_returns_json_schema():
    result = runner.invoke(app, ["schema", "show", "daily_summary", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["ok"] is True
    assert payload["schema_version"] == "garmin-claws.v1.schema"
    assert payload["data"]["$id"] == "https://iamjameskeane.github.io/garmin-claws/schemas/daily_summary.v1.json"
    assert payload["data"]["properties"]["schema_version"]["const"] == "garmin-claws.v1.daily_summary"


def test_daily_summary_normalizes_raw_stats(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CLAWS_TOKEN_DIR", str(tmp_path / ".garminconnect"))
    (tmp_path / ".garminconnect").mkdir()
    (tmp_path / ".garminconnect" / "garmin_tokens.json").write_text("{}")

    class FakeGarmin:
        def get_stats(self, day):
            assert day == "2026-04-29"
            return {
                "totalSteps": 8421,
                "totalDistanceMeters": 6500,
                "activeKilocalories": 532,
                "restingHeartRate": 52,
                "bodyBatteryMostRecentValue": 71,
                "averageStressLevel": 23,
            }

    monkeypatch.setattr("garmin_claws.cli.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["daily", "summary", "--date", "2026-04-29", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.daily_summary"
    assert payload["data"]["date"] == "2026-04-29"
    assert payload["data"]["metrics"]["steps"] == 8421
    assert payload["data"]["metrics"]["body_battery"] == 71
    assert "raw" not in payload["data"]


def test_activity_recent_normalizes_raw_activities(monkeypatch):
    class FakeGarmin:
        def get_activities(self, start, limit):
            assert (start, limit) == (0, 2)
            return [
                {
                    "activityId": 1,
                    "activityName": "Morning walk",
                    "activityType": {"typeKey": "walking"},
                    "startTimeLocal": "2026-04-28 08:00:00",
                    "duration": 1800,
                    "distance": 2400,
                    "averageHR": 105,
                }
            ]

    monkeypatch.setattr("garmin_claws.cli.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["activity", "recent", "--limit", "2", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.activity_list"
    activity = payload["data"]["activities"][0]
    assert activity == {
        "id": 1,
        "name": "Morning walk",
        "type": "walking",
        "start_time_local": "2026-04-28 08:00:00",
        "duration_seconds": 1800,
        "distance_meters": 2400,
        "average_heart_rate": 105,
    }
