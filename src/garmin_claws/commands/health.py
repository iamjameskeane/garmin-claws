from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.normalize import normalize_health_status
from garmin_claws.output import emit, resolve_day

health_app = typer.Typer(help="Health status and anomaly-oriented summaries")


@health_app.command("status")
def health_status(
    day: Annotated[str, typer.Option("--date", help="Date as YYYY-MM-DD, today, or yesterday.")] = "yesterday",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Interpret overnight health metrics against personal ranges."""
    resolved = resolve_day(day)
    raw = garmin_client().get_sleep_data(resolved)
    emit("health_status", normalize_health_status(raw, resolved), json_output)
