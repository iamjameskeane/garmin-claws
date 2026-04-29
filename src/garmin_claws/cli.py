from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

APP_SCHEMA_PREFIX = "garmin-claws.v1"

app = typer.Typer(help="Agent-ready Garmin Connect CLI")
auth_app = typer.Typer(help="Authenticate and manage Garmin Connect tokens")
daily_app = typer.Typer(help="Normalized daily Garmin summaries")
sleep_app = typer.Typer(help="Normalized Garmin sleep summaries")
activity_app = typer.Typer(help="Normalized Garmin activity commands")
health_app = typer.Typer(help="Health status and anomaly-oriented summaries")
training_app = typer.Typer(help="Training readiness, status, and load-balance summaries")
metrics_app = typer.Typer(help="Metric glossary and interpretation rules for agents")
flow_app = typer.Typer(help="Agent-oriented Garmin data flows")
schema_app = typer.Typer(help="Runtime JSON schema introspection")

app.add_typer(auth_app, name="auth")
app.add_typer(daily_app, name="daily")
app.add_typer(sleep_app, name="sleep")
app.add_typer(activity_app, name="activity")
app.add_typer(health_app, name="health")
app.add_typer(training_app, name="training")
app.add_typer(metrics_app, name="metrics")
app.add_typer(flow_app, name="flow")
app.add_typer(schema_app, name="schema")

console = Console(stderr=True)
STATE: dict[str, Any] = {"agent": False}


class ClawsError(Exception):
    def __init__(self, code: str, message: str, remediation: str, exit_code: int = 1):
        self.code = code
        self.message = message
        self.remediation = remediation
        self.exit_code = exit_code
        super().__init__(message)


@app.callback()
def main(
    agent: Annotated[
        bool,
        typer.Option(
            "--agent",
            help="Agent mode: no prompts, no rich formatting, structured JSON errors.",
        ),
    ] = False,
) -> None:
    STATE["agent"] = agent or os.environ.get("GARMIN_CLAWS_AGENT") == "1"


def token_dir() -> Path:
    return Path(os.environ.get("GARMIN_CLAWS_TOKEN_DIR", Path.home() / ".garminconnect")).expanduser()


def token_file() -> Path:
    return token_dir() / "garmin_tokens.json"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_day(value: str | None) -> str:
    if value in (None, "today"):
        return date.today().isoformat()
    if value == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    return value


def envelope(schema_name: str, data: Any, warnings: list[str] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": f"{APP_SCHEMA_PREFIX}.{schema_name}",
        "data": data,
        "warnings": warnings or [],
        "meta": meta or {"fetched_at": now_iso()},
    }


def error_envelope(error: ClawsError) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": f"{APP_SCHEMA_PREFIX}.error",
        "error": {
            "code": error.code,
            "message": error.message,
            "remediation": error.remediation,
        },
        "warnings": [],
        "meta": {},
    }


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def emit(schema_name: str, data: Any, json_output: bool, warnings: list[str] | None = None, meta: dict[str, Any] | None = None) -> None:
    payload = envelope(schema_name, data, warnings=warnings, meta=meta)
    if json_output or STATE["agent"]:
        print_json(payload)
    else:
        console.print(data)


def fail(error: ClawsError) -> None:
    if STATE["agent"]:
        print_json(error_envelope(error))
    else:
        console.print(error.message)
        console.print(error.remediation)
    raise typer.Exit(error.exit_code)


def missing_auth_error() -> ClawsError:
    path = token_file()
    return ClawsError(
        code="GARMIN_AUTH_MISSING",
        message=f"Garmin token file not found: {path}",
        remediation="Run `garmin-claws auth login --print-instructions`, then `garmin-claws auth import <zip>`.",
        exit_code=2,
    )


def require_tokens() -> Path:
    path = token_file()
    if not path.exists():
        fail(missing_auth_error())
    return path


def garmin_client():
    from garminconnect import Garmin

    require_tokens()
    client = Garmin()
    client.login(str(token_dir()))
    return client


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize_daily_stats(raw: dict[str, Any], day: str) -> dict[str, Any]:
    return {
        "date": day,
        "metrics": {
            "steps": raw.get("totalSteps"),
            "distance_meters": raw.get("totalDistanceMeters"),
            "active_kilocalories": raw.get("activeKilocalories"),
            "resting_heart_rate": raw.get("restingHeartRate"),
            "body_battery": raw.get("bodyBatteryMostRecentValue"),
            "stress_avg": raw.get("averageStressLevel"),
        },
        "source": {"provider": "garmin_connect"},
    }


def normalize_sleep(raw: dict[str, Any], day: str) -> dict[str, Any]:
    sleep_data = raw.get("dailySleepDTO", raw)
    return {
        "date": day,
        "metrics": {
            "sleep_seconds": sleep_data.get("sleepTimeSeconds") or sleep_data.get("sleepTimeSeconds"),
            "deep_sleep_seconds": sleep_data.get("deepSleepSeconds"),
            "light_sleep_seconds": sleep_data.get("lightSleepSeconds"),
            "rem_sleep_seconds": sleep_data.get("remSleepSeconds"),
            "awake_seconds": sleep_data.get("awakeSleepSeconds"),
            "sleep_score": nested_get(raw, "sleepScores", "overall", "value") or nested_get(raw, "dailySleepDTO", "sleepScores", "overall", "value") or sleep_data.get("sleepScore"),
        },
        "source": {"provider": "garmin_connect"},
    }


def normalize_activity(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("activityId"),
        "name": raw.get("activityName"),
        "type": nested_get(raw, "activityType", "typeKey") or raw.get("activityType"),
        "start_time_local": raw.get("startTimeLocal"),
        "duration_seconds": raw.get("duration"),
        "distance_meters": raw.get("distance"),
        "average_heart_rate": raw.get("averageHR"),
    }


METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "training_readiness": {
        "id": "training_readiness",
        "name": "Training Readiness",
        "plain_english": "Garmin's 0-100 estimate of how prepared the body is to handle training today.",
        "best_used_for": ["daily training gate", "maximum intensity selection", "recovery context"],
        "do_not_overinterpret": ["It cannot see muscular soreness or mental fatigue.", "It is not a workout prescription by itself."],
        "interpretation_rules": ["Use as a readiness gate, then use load focus to choose workout type.", "Garmin bases it on sleep score, recovery time, HRV status, acute load, sleep history, and stress history."],
        "flow_usage": ["trainability", "daily-coach", "recovery-check"],
    },
    "hrv_status": {
        "id": "hrv_status",
        "name": "HRV Status",
        "plain_english": "A trend-based recovery signal derived from overnight heart-rate variability.",
        "best_used_for": ["recovery trend", "fatigue detection", "illness or stress warning"],
        "do_not_overinterpret": ["Do not compare absolute HRV values between people.", "Do not overreact to one night."],
        "interpretation_rules": ["Compare against the user's personal baseline, not a population norm.", "Balanced usually supports training; low or unbalanced can reflect stress, illness, alcohol, dehydration, poor sleep, or training fatigue."],
        "flow_usage": ["recovery-check", "trainability", "illness-check"],
    },
    "load_focus": {
        "id": "load_focus",
        "name": "Training Load Focus",
        "plain_english": "Distribution of recent training load across low aerobic, high aerobic, and anaerobic buckets.",
        "best_used_for": ["workout type selection", "finding missing training stimulus", "weekly planning"],
        "do_not_overinterpret": ["It requires enough recent training history.", "It should be gated by recovery before adding intensity."],
        "interpretation_rules": ["Low aerobic supports base and recovery.", "High aerobic improves lactate threshold, VO2 max, and endurance.", "Anaerobic improves speed and anaerobic capacity but needs low-aerobic balance."],
        "flow_usage": ["load-diagnosis", "trainability", "daily-coach", "weekly-review"],
    },
    "sleep_score": {
        "id": "sleep_score",
        "name": "Sleep Score",
        "plain_english": "Garmin's composite score for last night's sleep quality and quantity.",
        "best_used_for": ["overnight recovery context", "training readiness interpretation"],
        "do_not_overinterpret": ["Duration alone is not recovery.", "Sleep score should be interpreted with HRV, overnight HR, stress, and Body Battery recharge."],
        "interpretation_rules": ["Use sleep as one contributor to training decisions, not the whole decision."],
        "flow_usage": ["sleep-recovery", "trainability", "daily-coach"],
    },
    "body_battery": {
        "id": "body_battery",
        "name": "Body Battery",
        "plain_english": "Garmin's estimate of general energy reserve based on sleep, stress, rest, and activity.",
        "best_used_for": ["daily pacing", "general energy", "non-sport fatigue context"],
        "do_not_overinterpret": ["It is less sport-specific than Training Readiness."],
        "interpretation_rules": ["Use for pacing work and life load; use Training Readiness and load focus for workouts."],
        "flow_usage": ["daily-coach", "energy-status"],
    },
    "acute_load": {
        "id": "acute_load",
        "name": "Acute Load",
        "plain_english": "Recent workout-induced training stress, usually interpreted over about a week.",
        "best_used_for": ["underload or overload detection", "ramp-rate context"],
        "do_not_overinterpret": ["It does not directly specify which workout type to do."],
        "interpretation_rules": ["Pair with chronic load/ACWR and readiness to avoid ramping too quickly."],
        "flow_usage": ["trainability", "weekly-review"],
    },
}


def _first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def normalize_range_metric(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value = _first_present(raw, ["value", "current", "avg", "average", "reading"])
    low = _first_present(raw, ["low", "min", "rangeLow", "typicalLow", "lowerBound"])
    high = _first_present(raw, ["high", "max", "rangeHigh", "typicalHigh", "upperBound"])
    status = "unknown"
    if value is not None and low is not None and high is not None:
        status = "within_range" if low <= value <= high else "out_of_range"
    return {"value": value, "range": [low, high], "unit": raw.get("unit"), "status": status}


def normalize_health_status(raw_sleep: dict[str, Any], day: str) -> dict[str, Any]:
    health = raw_sleep.get("healthStatus") or raw_sleep.get("healthStatusDTO") or raw_sleep.get("overnightMetrics") or {}
    aliases = {
        "heart_rate": ["heartRate", "heart_rate", "overnightHeartRate"],
        "hrv": ["hrv", "hrvStatus", "heartRateVariability"],
        "respiration": ["respiration", "respirationRate", "breathingRate"],
        "skin_temp": ["skinTemp", "skinTemperature", "skin_temp"],
        "pulse_ox": ["pulseOx", "pulseOX", "spo2", "pulse_ox"],
    }
    metrics: dict[str, Any] = {}
    for name, keys in aliases.items():
        raw_metric = next((health.get(key) for key in keys if isinstance(health, dict) and health.get(key) is not None), None)
        metrics[name] = normalize_range_metric(raw_metric) or {"value": None, "range": [None, None], "unit": None, "status": "unknown"}
    out = [name for name, metric in metrics.items() if metric["status"] == "out_of_range"]
    unknown = [name for name, metric in metrics.items() if metric["status"] == "unknown"]
    overall = "all_in_range" if not out and not unknown else "out_of_range" if out else "insufficient_data"
    return {
        "date": day,
        "overall": overall,
        "summary": "All core overnight health metrics are within your usual ranges." if overall == "all_in_range" else "Some health metrics are unavailable or out of range.",
        "metrics": metrics,
        "within_range": [name for name, metric in metrics.items() if metric["status"] == "within_range"],
        "out_of_range": out,
        "unknown": unknown,
    }


def sleep_score_from(raw_sleep: dict[str, Any]) -> Any:
    sleep_data = raw_sleep.get("dailySleepDTO", raw_sleep)
    return nested_get(raw_sleep, "sleepScores", "overall", "value") or sleep_data.get("sleepScore")


def normalize_sleep_recovery(raw_sleep: dict[str, Any], day: str) -> dict[str, Any]:
    summary = normalize_sleep(raw_sleep, day)
    health = normalize_health_status(raw_sleep, day)
    score = summary["metrics"].get("sleep_score")
    seconds = summary["metrics"].get("sleep_seconds")
    good_duration = seconds is not None and seconds >= 7 * 3600
    health_clear = health["overall"] == "all_in_range" or health["overall"] == "insufficient_data"
    if score is not None and score >= 80 and good_duration and health_clear:
        status = "good"
        impact = "supports_training"
        limiter = None
    elif score is not None and score < 60:
        status = "poor"
        impact = "reduce_intensity"
        limiter = "sleep_score"
    else:
        status = "fair"
        impact = "supports_easy_or_moderate_training"
        limiter = None if health_clear else "health_status"
    return {
        "date": day,
        "sleep_recovery": status,
        "training_impact": impact,
        "main_limiter": limiter,
        "sleep": summary["metrics"],
        "health_status": {"overall": health["overall"], "out_of_range": health["out_of_range"], "unknown": health["unknown"]},
    }


def _category(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    current = _first_present(raw, ["current", "value", "load", "currentLoad"])
    target_min = _first_present(raw, ["targetMin", "min", "low", "targetLow"])
    target_max = _first_present(raw, ["targetMax", "max", "high", "targetHigh"])
    if current is None or target_min is None or target_max is None:
        status = "unknown"
    elif current < target_min:
        status = "too_low"
    elif current > target_max:
        status = "too_high"
    else:
        status = "in_range"
    return {"current": current, "target_min": target_min, "target_max": target_max, "status": status}


def normalize_training_load_balance(raw_status: dict[str, Any], day: str) -> dict[str, Any]:
    lb = raw_status.get("loadBalance") or raw_status.get("loadFocus") or raw_status.get("exerciseLoadFocus")
    if lb is None and "mostRecentTrainingLoadBalance" in raw_status:
        device_map = nested_get(raw_status, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap") or {}
        lb = next((value for value in device_map.values() if value.get("primaryTrainingDevice")), None) or next(iter(device_map.values()), {})
        lb = {
            "lowAerobic": {
                "current": lb.get("monthlyLoadAerobicLow"),
                "targetMin": lb.get("monthlyLoadAerobicLowTargetMin"),
                "targetMax": lb.get("monthlyLoadAerobicLowTargetMax"),
            },
            "highAerobic": {
                "current": lb.get("monthlyLoadAerobicHigh"),
                "targetMin": lb.get("monthlyLoadAerobicHighTargetMin"),
                "targetMax": lb.get("monthlyLoadAerobicHighTargetMax"),
            },
            "anaerobic": {
                "current": lb.get("monthlyLoadAnaerobic"),
                "targetMin": lb.get("monthlyLoadAnaerobicTargetMin"),
                "targetMax": lb.get("monthlyLoadAnaerobicTargetMax"),
            },
            "trainingBalanceFeedbackPhrase": lb.get("trainingBalanceFeedbackPhrase"),
        }
    lb = lb or raw_status
    categories = {
        "low_aerobic": _category(lb.get("lowAerobic") or lb.get("low_aerobic") or lb.get("lowAerobicLoad")),
        "high_aerobic": _category(lb.get("highAerobic") or lb.get("high_aerobic") or lb.get("highAerobicLoad")),
        "anaerobic": _category(lb.get("anaerobic") or lb.get("anaerobicLoad")),
    }
    shortage_order = ["high_aerobic", "low_aerobic", "anaerobic"]
    diagnosis = "balanced"
    for name in shortage_order:
        if categories[name]["status"] == "too_low":
            diagnosis = f"{name}_shortage"
            break
    if all(cat["status"] == "unknown" for cat in categories.values()):
        diagnosis = "insufficient_data"
    recommendations = {
        "high_aerobic_shortage": ["tempo", "sweet_spot", "threshold-lite"],
        "low_aerobic_shortage": ["easy_zone_2", "recovery_ride", "long_walk"],
        "anaerobic_shortage": ["short_intervals", "hill_sprints", "strides"],
        "balanced": ["maintain_current_mix"],
        "insufficient_data": ["collect_more_activity_data"],
    }
    status_map = nested_get(raw_status, "mostRecentTrainingStatus", "latestTrainingStatusData") or {}
    primary_status = next((value for value in status_map.values() if value.get("primaryTrainingDevice")), None) or (next(iter(status_map.values()), {}) if status_map else {})
    acute_dto = primary_status.get("acuteTrainingLoadDTO", {})
    return {
        "date": day,
        "diagnosis": diagnosis,
        "categories": categories,
        "recommended_session_types": recommendations.get(diagnosis, []),
        "acute_load": raw_status.get("acuteTrainingLoad") or raw_status.get("acuteLoad") or acute_dto.get("dailyTrainingLoadAcute"),
        "chronic_load": raw_status.get("chronicTrainingLoad") or raw_status.get("chronicLoad") or acute_dto.get("dailyTrainingLoadChronic"),
        "acwr": raw_status.get("acuteChronicWorkloadRatio") or raw_status.get("acwr") or acute_dto.get("dailyAcuteChronicWorkloadRatio"),
    }


def normalize_training_readiness(raw: dict[str, Any] | list[dict[str, Any]], day: str) -> dict[str, Any]:
    if isinstance(raw, list):
        raw = next((item for item in raw if item.get("calendarDate") == day), None) or (raw[0] if raw else {})
    score = raw.get("score") or raw.get("trainingReadinessScore") or raw.get("readinessScore")
    return {
        "date": day,
        "score": score,
        "level": raw.get("level") or raw.get("readinessLevel") or raw.get("scoreLevel"),
        "feedback": raw.get("feedback") or raw.get("shortFeedback") or raw.get("feedbackLong"),
        "recovery_time_hours": raw.get("recoveryTime") or raw.get("recoveryTimeHours"),
    }


def build_trainability(readiness: dict[str, Any], sleep_recovery: dict[str, Any], load_balance: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    score = readiness.get("score")
    reasoning: list[str] = []
    cautions: list[str] = []
    decision = "unknown"
    max_intensity = "easy"
    if isinstance(score, (int, float)):
        if score >= 75:
            decision, max_intensity = "blue", "hard"
        elif score >= 50:
            decision, max_intensity = "green", "moderate"
        elif score >= 25:
            decision, max_intensity = "yellow", "easy"
        else:
            decision, max_intensity = "red", "recovery_only"
        reasoning.append(f"Training readiness is {score}.")
    if sleep_recovery.get("training_impact") == "supports_training":
        reasoning.append("Sleep recovery supports training.")
    elif sleep_recovery.get("sleep_recovery") == "poor":
        cautions.append("Sleep recovery is poor.")
    hrv = status.get("hrvStatus") or status.get("hrv_status")
    if isinstance(hrv, str) and hrv.upper() == "BALANCED":
        reasoning.append("HRV status is balanced.")
    diagnosis = load_balance.get("diagnosis")
    if diagnosis == "high_aerobic_shortage" and decision in {"green", "blue"}:
        max_intensity = "tempo"
        reasoning.append("High-aerobic load is below target")
    elif diagnosis == "low_aerobic_shortage":
        max_intensity = "easy"
        reasoning.append("Low-aerobic load is below target")
    elif diagnosis == "anaerobic_shortage" and decision == "blue":
        max_intensity = "intervals"
        reasoning.append("Anaerobic load is below target")
    return {
        "trainability": decision,
        "max_recommended_intensity": max_intensity,
        "reasoning": reasoning,
        "cautions": cautions,
        "readiness": readiness,
        "sleep_recovery": sleep_recovery,
        "load_balance": load_balance,
    }


def build_daily_coach(day: str, client: Any) -> dict[str, Any]:
    stats = normalize_daily_stats(client.get_stats(day), day)
    sleep_raw = client.get_sleep_data(day)
    health = normalize_health_status(sleep_raw, day)
    sleep_recovery = normalize_sleep_recovery(sleep_raw, day)
    raw_readiness = client.get_training_readiness(day)
    raw_status = client.get_training_status(day)
    readiness = normalize_training_readiness(raw_readiness, day)
    load_balance = normalize_training_load_balance(raw_status, day)
    trainability = build_trainability(readiness, sleep_recovery, load_balance, raw_status)
    intensity = trainability["max_recommended_intensity"]
    recommendation = {
        "type": "cycling" if intensity in {"tempo", "hard", "intervals"} else "easy aerobic",
        "intensity": intensity,
        "duration_minutes": 45 if intensity == "tempo" else 30,
        "rationale": trainability["reasoning"],
        "avoid": ["all-out intervals"] if intensity == "tempo" else [],
    }
    headline = f"{trainability['trainability'].capitalize()} trainability; best session is controlled {intensity}."
    return {
        "date": day,
        "headline": headline,
        "health": {"status": health["overall"], "out_of_range": health["out_of_range"]},
        "sleep": {"status": sleep_recovery["sleep_recovery"], "training_impact": sleep_recovery["training_impact"]},
        "training": {"readiness": readiness.get("score"), "load_gap": load_balance.get("diagnosis")},
        "daily": stats["metrics"],
        "trainability": trainability,
        "recommendation": recommendation,
    }


CAPABILITIES = [
    {
        "name": "daily summary",
        "description": "Fetch normalized daily Garmin metrics for one date.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.daily_summary",
    },
    {
        "name": "sleep summary",
        "description": "Fetch normalized sleep metrics for one date.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.sleep_summary",
    },
    {
        "name": "activity recent",
        "description": "Fetch normalized recent activities with limit/start pagination.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.activity_list",
    },
    {
        "name": "metrics explain",
        "description": "Return agent-facing definitions and interpretation rules for Garmin metrics.",
        "requires_auth": False,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.metric_definition",
    },
    {
        "name": "health status",
        "description": "Interpret core overnight health metrics against personal ranges.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.health_status",
    },
    {
        "name": "sleep recovery",
        "description": "Interpret whether last night's sleep supports training.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.sleep_recovery",
    },
    {
        "name": "training load-balance",
        "description": "Diagnose low/high aerobic and anaerobic load gaps.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.training_load_balance",
    },
    {
        "name": "flow plan",
        "description": "Describe an agent workflow without calling Garmin.",
        "requires_auth": False,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.flow_plan",
    },
    {
        "name": "flow run daily-coach",
        "description": "Run the composite daily coaching flow for health, sleep, readiness, load, and recommendation.",
        "requires_auth": True,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.daily_coach",
    },
    {
        "name": "schema show",
        "description": "Return a JSON schema embedded in garmin-claws.",
        "requires_auth": False,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.schema",
    },
]

SCHEMAS: dict[str, dict[str, Any]] = {
    "daily_summary": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/daily_summary.v1.json",
        "type": "object",
        "required": ["ok", "schema_version", "data", "warnings", "meta"],
        "properties": {
            "ok": {"const": True},
            "schema_version": {"const": "garmin-claws.v1.daily_summary"},
            "data": {"type": "object"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "meta": {"type": "object"},
        },
    },
    "sleep_summary": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/sleep_summary.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.sleep_summary"}},
    },
    "activity_list": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/activity_list.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.activity_list"}},
    },
    "error": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/error.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.error"}},
    },
    "metric_definition": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/metric_definition.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.metric_definition"}},
    },
    "health_status": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/health_status.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.health_status"}},
    },
    "sleep_recovery": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/sleep_recovery.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.sleep_recovery"}},
    },
    "training_load_balance": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/training_load_balance.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.training_load_balance"}},
    },
    "trainability": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/trainability.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.trainability"}},
    },
    "daily_coach": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://iamjameskeane.github.io/garmin-claws/schemas/daily_coach.v1.json",
        "type": "object",
        "properties": {"schema_version": {"const": "garmin-claws.v1.daily_coach"}},
    },
}


@auth_app.command("status")
def auth_status(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """Check whether Garmin Connect tokens are installed."""
    path = token_file()
    if not path.exists():
        fail(missing_auth_error())
    emit("auth_status", {"token_file": str(path), "authenticated": True}, json_output, meta={})


@auth_app.command("login")
def auth_login(
    print_instructions: Annotated[
        bool,
        typer.Option("--print-instructions", help="Print local-machine login instructions and exit."),
    ] = False,
) -> None:
    """Print the safe Garmin login flow.

    Garmin rate-limits cloud logins, so garmin-claws uses local token creation plus import.
    """
    instructions = """Run this on your local machine, not a cloud VM:

python3 -m venv garmin-auth-venv
source garmin-auth-venv/bin/activate
pip install -U "garminconnect[example]" curl_cffi
python3 - <<'PY'
from garminconnect import Garmin
from getpass import getpass
from pathlib import Path
out = Path.home() / ".garminconnect"
email = input("Garmin email: ").strip()
password = getpass("Garmin password: ")
g = Garmin(email=email, password=password, prompt_mfa=lambda: input("Garmin MFA/email code: ").strip())
g.login(str(out))
print(f"Tokens saved under: {out}")
PY
cd ~ && zip -r garminconnect-tokens.zip .garminconnect

Then copy the zip to the agent machine and run:
garmin-claws auth import garminconnect-tokens.zip
"""
    print(instructions)
    if not print_instructions:
        console.print("Tip: use --print-instructions in automation to avoid interactive login attempts.")


@auth_app.command("import")
def auth_import(archive: Path) -> None:
    """Import a zipped .garminconnect token directory."""
    if not archive.exists():
        fail(ClawsError("GARMIN_AUTH_ARCHIVE_MISSING", f"Archive not found: {archive}", "Pass the path to garminconnect-tokens.zip.", 3))
    target = token_dir()
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.unpack_archive(str(archive), str(target.parent))
    if not token_file().exists():
        fail(ClawsError("GARMIN_AUTH_IMPORT_INVALID", "Import finished but garmin_tokens.json was not found in the expected location.", "Zip the whole ~/.garminconnect directory and retry.", 3))
    target.chmod(0o700)
    token_file().chmod(0o600)
    console.print(f"Imported Garmin tokens to {token_file()}")


@app.command()
def capabilities(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """List agent-safe commands and their contracts."""
    emit("capabilities", {"commands": CAPABILITIES}, json_output, meta={})


@schema_app.command("list")
def schema_list(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """List embedded JSON schemas."""
    emit("schema_list", {"schemas": sorted(SCHEMAS)}, json_output, meta={})


@schema_app.command("show")
def schema_show(name: str, json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """Return an embedded JSON schema by name."""
    if name not in SCHEMAS:
        fail(ClawsError("GARMIN_SCHEMA_UNKNOWN", f"Unknown schema: {name}", f"Choose one of: {', '.join(sorted(SCHEMAS))}.", 3))
    emit("schema", SCHEMAS[name], json_output, meta={})


@daily_app.command("summary")
def daily_summary(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "today",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized daily Garmin metrics."""
    resolved = resolve_day(day)
    raw = garmin_client().get_stats(resolved)
    emit("daily_summary", normalize_daily_stats(raw, resolved), json_output)


@sleep_app.command("summary")
def sleep_summary(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "yesterday",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized Garmin sleep metrics."""
    resolved = resolve_day(day)
    raw = garmin_client().get_sleep_data(resolved)
    emit("sleep_summary", normalize_sleep(raw, resolved), json_output)


@activity_app.command("recent")
def activity_recent(
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 10,
    start: Annotated[int, typer.Option("--start", min=0)] = 0,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized recent activities."""
    raw = garmin_client().get_activities(start, limit)
    emit("activity_list", {"activities": [normalize_activity(item) for item in raw]}, json_output)


@metrics_app.command("list")
def metrics_list(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """List built-in Garmin metric definitions."""
    emit("metric_list", {"metrics": [{"id": key, "name": value["name"]} for key, value in sorted(METRIC_DEFINITIONS.items())]}, json_output, meta={})


@metrics_app.command("explain")
def metrics_explain(metric_id: str, json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """Explain a Garmin metric for agent reasoning."""
    if metric_id not in METRIC_DEFINITIONS:
        fail(ClawsError("GARMIN_METRIC_UNKNOWN", f"Unknown metric: {metric_id}", f"Choose one of: {', '.join(sorted(METRIC_DEFINITIONS))}.", 3))
    emit("metric_definition", METRIC_DEFINITIONS[metric_id], json_output, meta={})


@health_app.command("status")
def health_status(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "yesterday",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Interpret overnight health metrics against personal ranges."""
    resolved = resolve_day(day)
    raw = garmin_client().get_sleep_data(resolved)
    emit("health_status", normalize_health_status(raw, resolved), json_output)


@sleep_app.command("recovery")
def sleep_recovery(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "yesterday",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Interpret whether sleep supports training today."""
    resolved = resolve_day(day)
    raw = garmin_client().get_sleep_data(resolved)
    emit("sleep_recovery", normalize_sleep_recovery(raw, resolved), json_output)


@training_app.command("load-balance")
def training_load_balance(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "today",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Diagnose low/high aerobic and anaerobic load balance."""
    resolved = resolve_day(day)
    raw = garmin_client().get_training_status(resolved)
    emit("training_load_balance", normalize_training_load_balance(raw, resolved), json_output)


@training_app.command("readiness")
def training_readiness(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "today",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized training readiness."""
    resolved = resolve_day(day)
    raw = garmin_client().get_training_readiness(resolved)
    emit("training_readiness", normalize_training_readiness(raw, resolved), json_output)


@app.command()
def today(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False) -> None:
    """Compatibility alias for `daily summary --date today`."""
    raw = garmin_client().get_stats(date.today().isoformat())
    emit("daily_summary", normalize_daily_stats(raw, date.today().isoformat()), json_output)


@app.command()
def activities(
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 10,
    start: Annotated[int, typer.Option("--start", min=0)] = 0,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Compatibility alias for `activity recent`."""
    raw = garmin_client().get_activities(start, limit)
    emit("activity_list", {"activities": [normalize_activity(item) for item in raw]}, json_output)


@flow_app.command("plan")
def flow_plan(
    flow: Annotated[str, typer.Argument(help="Flow name, e.g. daily-brief.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Describe the commands an agent should run for a named flow."""
    plans: dict[str, dict[str, Any]] = {
        "daily-brief": {
            "flow": "daily-brief",
            "read_only": True,
            "requires_auth": True,
            "commands": [
                "garmin-claws daily summary --date today --json",
                "garmin-claws sleep summary --date yesterday --json",
                "garmin-claws activity recent --limit 5 --json",
            ],
            "output": "Summarize readiness, sleep, load, and recent movement without medical claims.",
        }
    }
    if flow not in plans:
        fail(ClawsError("GARMIN_FLOW_UNKNOWN", f"Unknown flow: {flow}", f"Choose one of: {', '.join(sorted(plans))}.", 3))
    emit("flow_plan", plans[flow], json_output, meta={})


@flow_app.command("run")
def flow_run(
    flow: Annotated[str, typer.Argument(help="Flow name, e.g. trainability or daily-coach.")],
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "today",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Run a composite agent-oriented Garmin flow."""
    resolved = resolve_day(day)
    client = garmin_client()
    if flow == "trainability":
        sleep_day = resolved
        sleep_raw = client.get_sleep_data(sleep_day)
        sleep_rec = normalize_sleep_recovery(sleep_raw, sleep_day)
        raw_readiness = client.get_training_readiness(resolved)
        raw_status = client.get_training_status(resolved)
        data = build_trainability(
            normalize_training_readiness(raw_readiness, resolved),
            sleep_rec,
            normalize_training_load_balance(raw_status, resolved),
            raw_status,
        )
        emit("trainability", data, json_output)
        return
    if flow == "daily-coach":
        emit("daily_coach", build_daily_coach(resolved, client), json_output)
        return
    fail(ClawsError("GARMIN_FLOW_UNKNOWN", f"Unknown flow: {flow}", "Choose one of: trainability, daily-coach.", 3))


if __name__ == "__main__":
    try:
        app()
    except BrokenPipeError:
        sys.exit(0)
