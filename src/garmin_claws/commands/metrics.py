from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.constants import METRIC_DEFINITIONS
from garmin_claws.errors import ClawsError
from garmin_claws.output import emit, fail

metrics_app = typer.Typer(help="Metric glossary and interpretation rules for agents")


@metrics_app.command("list")
def metrics_list(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """List built-in Garmin metric definitions."""
    emit(
        "metric_list",
        {"metrics": [{"id": key, "name": value["name"]} for key, value in sorted(METRIC_DEFINITIONS.items())]},
        json_output,
        meta={},
    )


@metrics_app.command("explain")
def metrics_explain(
    metric_id: str,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Explain a Garmin metric for agent reasoning."""
    if metric_id not in METRIC_DEFINITIONS:
        fail(ClawsError("GARMIN_METRIC_UNKNOWN", f"Unknown metric: {metric_id}", f"Choose one of: {', '.join(sorted(METRIC_DEFINITIONS))}.", 3))
    emit("metric_definition", METRIC_DEFINITIONS[metric_id], json_output, meta={})
