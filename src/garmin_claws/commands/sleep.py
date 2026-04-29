from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.normalize import normalize_sleep, normalize_sleep_recovery
from garmin_claws.output import emit, resolve_day

sleep_app = typer.Typer(help="Normalized Garmin sleep summaries")


@sleep_app.command("summary")
def sleep_summary(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "yesterday",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized Garmin sleep metrics."""
    resolved = resolve_day(day)
    raw = garmin_client().get_sleep_data(resolved)
    emit("sleep_summary", normalize_sleep(raw, resolved), json_output)


@sleep_app.command("recovery")
def sleep_recovery(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "yesterday",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Interpret whether sleep supports training today."""
    resolved = resolve_day(day)
    raw = garmin_client().get_sleep_data(resolved)
    emit("sleep_recovery", normalize_sleep_recovery(raw, resolved), json_output)
