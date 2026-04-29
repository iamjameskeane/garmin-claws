from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import typer

from garmin_claws.errors import ClawsError
from garmin_claws.output import console, fail


def token_dir() -> Path:
    return Path(os.environ.get("GARMIN_CLAWS_TOKEN_DIR", Path.home() / ".garminconnect")).expanduser()


def token_file() -> Path:
    return token_dir() / "garmin_tokens.json"


def missing_auth_error() -> ClawsError:
    path = token_file()
    return ClawsError(
        code="GARMIN_AUTH_MISSING",
        message=f"Garmin token file not found: {path}",
        remediation="Run `garmin-claws auth login --print-instructions`, then `garmin-claws auth import <zip>`.",
        exit_code=2,
    )


def require_tokens() -> Path:
    path = token_file()
    if not path.exists():
        fail(missing_auth_error())
    return path


def garmin_client():
    from garminconnect import Garmin

    require_tokens()
    client = Garmin()
    client.login(str(token_dir()))
    return client
