# garmin-claws

Agent-ready Garmin Connect CLI and Hermes skill package.

`garmin-claws` gives agents a stable, safe interface over Garmin Connect data: authenticate once, then expose predictable commands for daily summaries, activities, sleep, recovery, and higher-level flows.

## Why this exists

Garmin Connect is useful but awkward for agents:

- login is brittle from cloud hosts because Garmin rate-limits cloud IPs;
- raw API responses are large and inconsistent;
- agents need repeatable commands, JSON output, and clear safety boundaries;
- workflows like "daily brief" should be named flows rather than bespoke scripts.

## Install for development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Commands

```bash
# Auth/token management
garmin-claws auth status
garmin-claws auth login --print-instructions
garmin-claws auth import garminconnect-tokens.zip

# Data access
garmin-claws today --json
garmin-claws sleep 2026-04-28 --json
garmin-claws activities --limit 10 --json

# Agent flows
garmin-claws flow plan daily-brief --json
```

## Auth model

Do **not** repeatedly attempt Garmin login from a cloud VM. The safe flow is:

1. Run `garmin-claws auth login --print-instructions`.
2. Follow the printed Python snippet on your local laptop.
3. Zip `~/.garminconnect`.
4. Transfer the zip to the agent machine.
5. Run `garmin-claws auth import garminconnect-tokens.zip`.

By default tokens live at `~/.garminconnect/garmin_tokens.json`. Override with `GARMIN_CLAWS_TOKEN_DIR`.

## Status

Initial scaffold: CLI, tests, auth instructions, direct data commands, and a first `daily-brief` flow plan.
