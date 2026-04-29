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

    monkeypatch.setattr("garmin_claws.commands.daily.garmin_client", lambda: FakeGarmin())

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

    monkeypatch.setattr("garmin_claws.commands.activity.garmin_client", lambda: FakeGarmin())

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


def test_metrics_explain_returns_agent_context_without_auth():
    result = runner.invoke(app, ["metrics", "explain", "hrv_status", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.metric_definition"
    data = payload["data"]
    assert data["id"] == "hrv_status"
    assert "personal baseline" in " ".join(data["interpretation_rules"]).lower()
    assert "recovery-check" in data["flow_usage"]


def test_metrics_list_includes_decision_relevant_metrics():
    result = runner.invoke(app, ["metrics", "list", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    metric_ids = {item["id"] for item in payload["data"]["metrics"]}
    assert {"training_readiness", "hrv_status", "load_focus", "sleep_score", "body_battery"}.issubset(metric_ids)


def test_health_status_interprets_core_overnight_metrics(monkeypatch):
    class FakeGarmin:
        def get_sleep_data(self, day):
            assert day == "2026-04-29"
            return {
                "healthStatus": {
                    "heartRate": {"value": 65, "low": 61, "high": 71, "unit": "bpm"},
                    "hrv": {"value": 46, "low": 41, "high": 57, "unit": "ms"},
                    "respiration": {"value": 14.3, "low": 13.4, "high": 15.6, "unit": "brpm"},
                    "skinTemp": {"value": -0.1, "low": -0.8, "high": 0.8, "unit": "c_delta"},
                    "pulseOx": {"value": 98, "low": 90, "high": 100, "unit": "%"},
                }
            }

    monkeypatch.setattr("garmin_claws.commands.health.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["health", "status", "--date", "2026-04-29", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.health_status"
    assert payload["data"]["overall"] == "all_in_range"
    assert payload["data"]["out_of_range"] == []
    assert payload["data"]["metrics"]["hrv"]["status"] == "within_range"


def test_training_load_balance_identifies_high_aerobic_shortage(monkeypatch):
    class FakeGarmin:
        def get_training_status(self, day):
            assert day == "2026-04-29"
            return {
                "loadBalance": {
                    "lowAerobic": {"current": 624, "targetMin": 146, "targetMax": 357},
                    "highAerobic": {"current": 53, "targetMin": 240, "targetMax": 451},
                    "anaerobic": {"current": 36, "targetMin": 0, "targetMax": 211},
                },
                "acuteTrainingLoad": 235,
                "chronicTrainingLoad": 187,
                "acuteChronicWorkloadRatio": 1.2,
            }

    monkeypatch.setattr("garmin_claws.commands.training.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["training", "load-balance", "--date", "2026-04-29", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.training_load_balance"
    assert payload["data"]["diagnosis"] == "high_aerobic_shortage"
    assert "tempo" in payload["data"]["recommended_session_types"]
    assert payload["data"]["categories"]["low_aerobic"]["status"] == "too_high"


def test_sleep_recovery_combines_sleep_and_overnight_metrics(monkeypatch):
    class FakeGarmin:
        def get_sleep_data(self, day):
            return {
                "dailySleepDTO": {"sleepTimeSeconds": 8 * 3600, "sleepScore": 82},
                "sleepScores": {"overall": {"value": 82}},
                "healthStatus": {
                    "heartRate": {"value": 65, "low": 61, "high": 71, "unit": "bpm"},
                    "hrv": {"value": 46, "low": 41, "high": 57, "unit": "ms"},
                    "respiration": {"value": 14.3, "low": 13.4, "high": 15.6, "unit": "brpm"},
                    "skinTemp": {"value": -0.1, "low": -0.8, "high": 0.8, "unit": "c_delta"},
                    "pulseOx": {"value": 98, "low": 90, "high": 100, "unit": "%"},
                },
            }

    monkeypatch.setattr("garmin_claws.commands.sleep.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["sleep", "recovery", "--date", "2026-04-29", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.sleep_recovery"
    assert payload["data"]["sleep_recovery"] == "good"
    assert payload["data"]["training_impact"] == "supports_training"
    assert payload["data"]["main_limiter"] is None


def test_trainability_flow_gates_intensity_from_recovery_and_load(monkeypatch):
    class FakeGarmin:
        def get_training_readiness(self, day):
            return {"score": 72, "level": "MODERATE", "feedback": "RECOVERED_AND_READY", "recoveryTime": 1}

        def get_training_status(self, day):
            return {
                "hrvStatus": "BALANCED",
                "acuteChronicWorkloadRatio": 1.2,
                "loadBalance": {
                    "lowAerobic": {"current": 624, "targetMin": 146, "targetMax": 357},
                    "highAerobic": {"current": 53, "targetMin": 240, "targetMax": 451},
                    "anaerobic": {"current": 36, "targetMin": 0, "targetMax": 211},
                },
            }

        def get_sleep_data(self, day):
            return {"dailySleepDTO": {"sleepTimeSeconds": 8 * 3600, "sleepScore": 82}, "sleepScores": {"overall": {"value": 82}}, "healthStatus": {}}

    monkeypatch.setattr("garmin_claws.commands.flow.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["flow", "run", "trainability", "--date", "2026-04-29", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.trainability"
    assert payload["data"]["trainability"] == "green"
    assert payload["data"]["max_recommended_intensity"] == "tempo"
    assert "High-aerobic load is below target" in payload["data"]["reasoning"]


def test_daily_coach_flow_returns_single_agent_friendly_recommendation(monkeypatch):
    class FakeGarmin:
        def get_stats(self, day):
            return {"bodyBatteryMostRecentValue": 78, "averageStressLevel": 18, "restingHeartRate": 58, "totalSteps": 4000}

        def get_sleep_data(self, day):
            return {
                "dailySleepDTO": {"sleepTimeSeconds": 8 * 3600, "sleepScore": 82},
                "sleepScores": {"overall": {"value": 82}},
                "healthStatus": {
                    "heartRate": {"value": 65, "low": 61, "high": 71, "unit": "bpm"},
                    "hrv": {"value": 46, "low": 41, "high": 57, "unit": "ms"},
                    "respiration": {"value": 14.3, "low": 13.4, "high": 15.6, "unit": "brpm"},
                    "skinTemp": {"value": -0.1, "low": -0.8, "high": 0.8, "unit": "c_delta"},
                    "pulseOx": {"value": 98, "low": 90, "high": 100, "unit": "%"},
                },
            }

        def get_training_readiness(self, day):
            return {"score": 72, "level": "MODERATE", "feedback": "RECOVERED_AND_READY", "recoveryTime": 1}

        def get_training_status(self, day):
            return {
                "hrvStatus": "BALANCED",
                "acuteChronicWorkloadRatio": 1.2,
                "loadBalance": {
                    "lowAerobic": {"current": 624, "targetMin": 146, "targetMax": 357},
                    "highAerobic": {"current": 53, "targetMin": 240, "targetMax": 451},
                    "anaerobic": {"current": 36, "targetMin": 0, "targetMax": 211},
                },
            }

        def get_activities(self, start, limit):
            return []

    monkeypatch.setattr("garmin_claws.commands.flow.garmin_client", lambda: FakeGarmin())

    result = runner.invoke(app, ["flow", "run", "daily-coach", "--date", "2026-04-29", "--json"])

    assert result.exit_code == 0
    payload = parse_json(result)
    assert payload["schema_version"] == "garmin-claws.v1.daily_coach"
    assert "tempo" in payload["data"]["headline"].lower()
    assert payload["data"]["recommendation"]["intensity"] == "tempo"
    assert payload["data"]["health"]["status"] == "all_in_range"
