from __future__ import annotations

from typing import Any


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
            "sleep_score": nested_get(raw, "sleepScores", "overall", "value")
            or nested_get(raw, "dailySleepDTO", "sleepScores", "overall", "value")
            or sleep_data.get("sleepScore"),
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
        raw_metric = next(
            (health.get(key) for key in keys if isinstance(health, dict) and health.get(key) is not None), None
        )
        metrics[name] = normalize_range_metric(raw_metric) or {
            "value": None,
            "range": [None, None],
            "unit": None,
            "status": "unknown",
        }
    out = [name for name, metric in metrics.items() if metric["status"] == "out_of_range"]
    unknown = [name for name, metric in metrics.items() if metric["status"] == "unknown"]
    overall = (
        "all_in_range" if not out and not unknown else "out_of_range" if out else "insufficient_data"
    )
    return {
        "date": day,
        "overall": overall,
        "summary": (
            "All core overnight health metrics are within your usual ranges."
            if overall == "all_in_range"
            else "Some health metrics are unavailable or out of range."
        ),
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
        device_map = (
            nested_get(raw_status, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap") or {}
        )
        lb = next((value for value in device_map.values() if value.get("primaryTrainingDevice")), None) or next(
            iter(device_map.values()), {}
        )
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
    primary_status = (
        next((value for value in status_map.values() if value.get("primaryTrainingDevice")), None)
        or (next(iter(status_map.values()), {}) if status_map else {})
    )
    acute_dto = primary_status.get("acuteTrainingLoadDTO", {})
    return {
        "date": day,
        "diagnosis": diagnosis,
        "categories": categories,
        "recommended_session_types": recommendations.get(diagnosis, []),
        "acute_load": raw_status.get("acuteTrainingLoad")
        or raw_status.get("acuteLoad")
        or acute_dto.get("dailyTrainingLoadAcute"),
        "chronic_load": raw_status.get("chronicTrainingLoad")
        or raw_status.get("chronicLoad")
        or acute_dto.get("dailyTrainingLoadChronic"),
        "acwr": raw_status.get("acuteChronicWorkloadRatio")
        or raw_status.get("acwr")
        or acute_dto.get("dailyAcuteChronicWorkloadRatio"),
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


def build_trainability(
    readiness: dict[str, Any],
    sleep_recovery: dict[str, Any],
    load_balance: dict[str, Any],
    status: dict[str, Any],
) -> dict[str, Any]:
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
