from __future__ import annotations

from typing import Annotated, Any

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.errors import ClawsError
from garmin_claws.normalize import (
    build_daily_coach,
    build_trainability,
    normalize_sleep_recovery,
    normalize_training_load_balance,
    normalize_training_readiness,
)
from garmin_claws.output import emit, fail, resolve_day

flow_app = typer.Typer(help="Agent-oriented Garmin data flows")


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
