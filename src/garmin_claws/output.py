from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from rich.console import Console
import typer

from garmin_claws.constants import APP_SCHEMA_PREFIX
from garmin_claws.errors import ClawsError

console = Console(stderr=True)
STATE: dict[str, Any] = {"agent": False}


def resolve_day(value: str | None) -> str:
    if value in (None, "today"):
        return date.today().isoformat()
    if value == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    return value


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def envelope(
    schema_name: str, data: Any, warnings: list[str] | None = None, meta: dict[str, Any] | None = None
) -> dict[str, Any]:
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


def emit(
    schema_name: str,
    data: Any,
    json_output: bool,
    warnings: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
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
