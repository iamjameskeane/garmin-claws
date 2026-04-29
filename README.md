# garmin-claws

Agent-ready Garmin Connect CLI and Hermes skill package.

`garmin-claws` is a small, stable Garmin data API for agents, exposed as a CLI. It hides Garmin Connect auth/API weirdness behind predictable commands, JSON response envelopes, structured errors, runtime introspection, and bundled agent instructions.

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
pytest -q
```

## Agent-first design

The CLI follows these contracts:

- `--json` emits a stable response envelope.
- `--agent` enables no-prompt agent mode and structured JSON errors.
- stdout is reserved for machine-readable payloads in JSON mode.
- diagnostics and human help go to stderr.
- normalized commands are preferred over raw Garmin blobs.
- `capabilities` and `schema` commands make the CLI self-describing.

Success envelope:

```json
{
  "ok": true,
  "schema_version": "garmin-claws.v1.daily_summary",
  "data": {},
  "warnings": [],
  "meta": {"fetched_at": "2026-04-29T11:30:00Z"}
}
```

Error envelope in agent mode:

```json
{
  "ok": false,
  "schema_version": "garmin-claws.v1.error",
  "error": {
    "code": "GARMIN_AUTH_MISSING",
    "message": "Garmin token file not found: ...",
    "remediation": "Run `garmin-claws auth login --print-instructions`, then `garmin-claws auth import <zip>`."
  },
  "warnings": [],
  "meta": {}
}
```

## Commands

```bash
# Auth/token management
garmin-claws auth status
garmin-claws --agent auth status
garmin-claws auth login --print-instructions
garmin-claws auth import garminconnect-tokens.zip

# Introspection
garmin-claws capabilities --json
garmin-claws schema list --json
garmin-claws schema show daily_summary --json

# Normalized data access
garmin-claws daily summary --date today --json
garmin-claws sleep summary --date yesterday --json
garmin-claws activity recent --limit 10 --json

# Compatibility aliases
garmin-claws today --json
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

## Schemas

Schema files live in `schemas/` and are also available at runtime:

```bash
garmin-claws schema show daily_summary --json
garmin-claws schema show sleep_summary --json
garmin-claws schema show activity_list --json
garmin-claws schema show error --json
```

## Status

Current scaffold: normalized daily/sleep/activity commands, agent response envelopes, structured errors, capabilities/schema introspection, a `daily-brief` flow plan, tests, and a bundled Hermes skill.
