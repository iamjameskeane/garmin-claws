from __future__ import annotations

from typing import Annotated

import typer

from garmin_claws.constants import SCHEMAS
from garmin_claws.errors import ClawsError
from garmin_claws.output import emit, fail

schema_app = typer.Typer(help="Runtime JSON schema introspection")


@schema_app.command("list")
def schema_list(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """List embedded JSON schemas."""
    emit("schema_list", {"schemas": sorted(SCHEMAS)}, json_output, meta={})


@schema_app.command("show")
def schema_show(
    name: str,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Return an embedded JSON schema by name."""
    if name not in SCHEMAS:
        fail(ClawsError("GARMIN_SCHEMA_UNKNOWN", f"Unknown schema: {name}", f"Choose one of: {', '.join(sorted(SCHEMAS))}.", 3))
    emit("schema", SCHEMAS[name], json_output, meta={})
