from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer

from garmin_claws.auth import missing_auth_error, token_dir, token_file
from garmin_claws.errors import ClawsError
from garmin_claws.output import console, emit, fail

auth_app = typer.Typer(help="Authenticate and manage Garmin Connect tokens")


@auth_app.command("status")
def auth_status(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON for agents.")] = False,
) -> None:
    """Check whether Garmin Connect tokens are installed."""
    path = token_file()
    if not path.exists():
        fail(missing_auth_error())
    emit("auth_status", {"token_file": str(path), "authenticated": True}, json_output, meta={})


@auth_app.command("login")
def auth_login(
    print_instructions: Annotated[
        bool,
        typer.Option("--print-instructions", help="Print local-machine login instructions and exit."),
    ] = False,
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
    print(instructions)
    if not print_instructions:
        console.print("Tip: use --print-instructions in automation to avoid interactive login attempts.")


@auth_app.command("import")
def auth_import(archive: Path) -> None:
    """Import a zipped .garminconnect token directory."""
    if not archive.exists():
        fail(ClawsError("GARMIN_AUTH_ARCHIVE_MISSING", f"Archive not found: {archive}", "Pass the path to garminconnect-tokens.zip.", 3))
    target = token_dir()
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.unpack_archive(str(archive), str(target.parent))
    if not token_file().exists():
        fail(ClawsError("GARMIN_AUTH_IMPORT_INVALID", "Import finished but garmin_tokens.json was not found in the expected location.", "Zip the whole ~/.garminconnect directory and retry.", 3))
    target.chmod(0o700)
    token_file().chmod(0o600)
    console.print(f"Imported Garmin tokens to {token_file()}")
