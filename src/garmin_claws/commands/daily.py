from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.normalize import normalize_daily_stats
from garmin_claws.output import emit, resolve_day

daily_app = typer.Typer(help="Normalized daily Garmin summaries")


@daily_app.command("summary")
def daily_summary(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "today",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized daily Garmin metrics."""
    resolved = resolve_day(day)
    raw = garmin_client().get_stats(resolved)
    emit("daily_summary", normalize_daily_stats(raw, resolved), json_output)
