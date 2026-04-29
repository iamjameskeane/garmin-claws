from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.auth import garmin_client
from garmin_claws.normalize import normalize_activity
from garmin_claws.output import emit

activity_app = typer.Typer(help="Normalized Garmin activity commands")


@activity_app.command("recent")
def activity_recent(
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 10,
    start: Annotated[int, typer.Option("--start", min=0)] = 0,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Fetch normalized recent activities."""
    raw = garmin_client().get_activities(start, limit)
    emit("activity_list", {"activities": [normalize_activity(item) for item in raw]}, json_output)
