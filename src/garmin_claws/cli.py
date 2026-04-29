from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

app = typer.Typer(help="Agent-ready Garmin Connect CLI")
auth_app = typer.Typer(help="Authenticate and manage Garmin Connect tokens")
flow_app = typer.Typer(help="Agent-oriented Garmin data flows")
app.add_typer(auth_app, name="auth")
app.add_typer(flow_app, name="flow")
console = Console()


def token_dir() -> Path:
    return Path(os.environ.get("GARMIN_CLAWS_TOKEN_DIR", Path.home() / ".garminconnect")).expanduser()


def token_file() -> Path:
    return token_dir() / "garmin_tokens.json"


def require_tokens() -> Path:
    path = token_file()
    if not path.exists():
        console.print(f"Garmin token file not found: {path}")
        console.print("Run `garmin-claws auth login` on a trusted local machine, then import tokens.")
        raise typer.Exit(1)
    return path


def garmin_client():
    from garminconnect import Garmin

    require_tokens()
    client = Garmin()
    client.login(str(token_dir()))
    return client


@auth_app.command("status")
def auth_status() -> None:
    """Check whether Garmin Connect tokens are installed."""
    path = token_file()
    if not path.exists():
        console.print(f"Garmin token file not found: {path}")
        console.print("Run `garmin-claws auth login` on a trusted local machine, then import tokens.")
        raise typer.Exit(1)
    console.print(f"Garmin tokens found: {path}")


@auth_app.command("login")
def auth_login(
    print_instructions: bool = typer.Option(
        False, "--print-instructions", help="Print local-machine login instructions and exit."
    ),
) -> None:
    """Print the safe Garmin login flow.

    Garmin rate-limits cloud logins, so garmin-claws uses local token creation plus import.
    """
    instructions = """Run this on your local machine, not a cloud VM:

python3 -m venv garmin-auth-venv
source garmin-auth-venv/bin/activate
pip install -U "garminconnect[example]" curl_cffi
python3 - <<'PY'
from garminconnect import Garmin
from getpass import getpass
from pathlib import Path
out = Path.home() / ".garminconnect"
email = input("Garmin email: ").strip()
password = getpass("Garmin password: ")
g = Garmin(email=email, password=password, prompt_mfa=lambda: input("Garmin MFA/email code: ").strip())
g.login(str(out))
print(f"Tokens saved under: {out}")
PY
cd ~ && zip -r garminconnect-tokens.zip .garminconnect

Then copy the zip to the agent machine and run:
garmin-claws auth import garminconnect-tokens.zip
"""
    console.print(instructions)
    if not print_instructions:
        console.print("Tip: use --print-instructions in automation to avoid interactive login attempts.")


@auth_app.command("import")
def auth_import(archive: Path) -> None:
    """Import a zipped .garminconnect token directory."""
    if not archive.exists():
        console.print(f"Archive not found: {archive}")
        raise typer.Exit(1)
    target = token_dir()
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.unpack_archive(str(archive), str(target.parent))
    if not token_file().exists():
        console.print("Import finished but garmin_tokens.json was not found in the expected location.")
        raise typer.Exit(1)
    target.chmod(0o700)
    token_file().chmod(0o600)
    console.print(f"Imported Garmin tokens to {token_file()}")


@app.command()
def today(json_output: bool = typer.Option(False, "--json", help="Emit JSON for agents.")) -> None:
    """Fetch today's Garmin daily stats."""
    client = garmin_client()
    data = client.get_stats(date.today().isoformat())
    emit(data, json_output)


@app.command()
def sleep(
    day: str = typer.Argument(..., help="Date in YYYY-MM-DD form."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON for agents."),
) -> None:
    """Fetch sleep data for a date."""
    data = garmin_client().get_sleep_data(day)
    emit(data, json_output)


@app.command()
def activities(
    limit: int = typer.Option(10, "--limit", min=1, max=100),
    start: int = typer.Option(0, "--start", min=0),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON for agents."),
) -> None:
    """Fetch recent activities."""
    data = garmin_client().get_activities(start, limit)
    emit(data, json_output)


@flow_app.command("plan")
def flow_plan(
    flow: str = typer.Argument(..., help="Flow name, e.g. daily-brief."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON for agents."),
) -> None:
    """Describe the commands an agent should run for a named flow."""
    plans: dict[str, dict[str, Any]] = {
        "daily-brief": {
            "flow": "daily-brief",
            "commands": [
                "garmin-claws today --json",
                "garmin-claws sleep $(date -I -d yesterday) --json",
                "garmin-claws activities --limit 5 --json",
            ],
            "output": "Summarize readiness, sleep, load, and recent movement without medical claims.",
        }
    }
    if flow not in plans:
        console.print(f"Unknown flow: {flow}")
        raise typer.Exit(1)
    emit(plans[flow], json_output)


def emit(data: Any, json_output: bool) -> None:
    if json_output:
        console.print(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        console.print(data)


if __name__ == "__main__":
    app()
