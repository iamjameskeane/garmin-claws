from __future__ import annotations

import os
import sys
from datetime import date
from typing import Annotated

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.constants import CAPABILITIES
from garmin_claws.normalize import normalize_activity, normalize_daily_stats
from garmin_claws.output import STATE, emit

app = typer.Typer(help="Agent-ready Garmin Connect CLI")

from garmin_claws.commands.activity import activity_app
from garmin_claws.commands.auth import auth_app
from garmin_claws.commands.daily import daily_app
from garmin_claws.commands.flow import flow_app
from garmin_claws.commands.health import health_app
from garmin_claws.commands.metrics import metrics_app
from garmin_claws.commands.schema import schema_app
from garmin_claws.commands.sleep import sleep_app
from garmin_claws.commands.training import training_app

app.add_typer(auth_app, name="auth")
app.add_typer(daily_app, name="daily")
app.add_typer(sleep_app, name="sleep")
app.add_typer(activity_app, name="activity")
app.add_typer(health_app, name="health")
app.add_typer(training_app, name="training")
app.add_typer(metrics_app, name="metrics")
app.add_typer(flow_app, name="flow")
app.add_typer(schema_app, name="schema")


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


@app.command()
def capabilities(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """List agent-safe commands and their contracts."""
    emit("capabilities", {"commands": CAPABILITIES}, json_output, meta={})


@app.command()
def today(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
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


if __name__ == "__main__":
    try:
        app()
    except BrokenPipeError:
        sys.exit(0)
