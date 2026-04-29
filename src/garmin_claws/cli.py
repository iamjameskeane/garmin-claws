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
flow_app = typer.Typer(help="Agent-oriented Garmin data flows")
schema_app = typer.Typer(help="Runtime JSON schema introspection")

app.add_typer(auth_app, name="auth")
app.add_typer(daily_app, name="daily")
app.add_typer(sleep_app, name="sleep")
app.add_typer(activity_app, name="activity")
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
            "sleep_score": nested_get(raw, "sleepScores", "overall", "value") or sleep_data.get("sleepScore"),
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
        "name": "flow plan",
        "description": "Describe an agent workflow without calling Garmin.",
        "requires_auth": False,
        "safe": True,
        "read_only": True,
        "output_schema": f"{APP_SCHEMA_PREFIX}.flow_plan",
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


if __name__ == "__main__":
    try:
        app()
    except BrokenPipeError:
        sys.exit(0)
