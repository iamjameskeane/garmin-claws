from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.normalize import normalize_training_load_balance, normalize_training_readiness
from garmin_claws.output import emit, resolve_day

training_app = typer.Typer(help="Training readiness, status, and load-balance summaries")


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
