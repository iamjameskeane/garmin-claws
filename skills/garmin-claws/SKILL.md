---
name: garmin-claws
description: Agent-ready Garmin Connect CLI. Use for fetching normalized Garmin daily, sleep, and activity data; discovering command/schema contracts; and planning safe health/fitness briefing flows via stable JSON commands.
tags: [garmin, fitness, health-data, cli, agents, hermes]
triggers:
  - garmin-claws
  - Garmin Connect
  - Garmin data
  - fitness brief
  - sleep data
  - activity data
---

# garmin-claws

Use `garmin-claws` when the user wants an agent to inspect Garmin Connect data or run a named Garmin-oriented flow.

## Safety boundaries

- Do not make medical claims or diagnoses.
- Treat Garmin data as user-owned private health-adjacent data.
- Prefer concise summaries with uncertainty: sleep, activity, load, recovery signals.
- Do not print OAuth tokens or token file contents.
- If auth is missing, explain the local-machine token transfer flow.
- Prefer normalized commands over raw Garmin API responses.

## Agent mode contract

For automation, prefer:

```bash
garmin-claws --agent <command>
```

or pass `--json` on individual commands. In agent mode:

- no prompts are attempted;
- JSON is emitted to stdout;
- failures use `garmin-claws.v1.error` envelopes;
- human diagnostics go to stderr;
- exit codes are meaningful enough for branching.

Error example:

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

## Auth

Check auth in agent mode:

```bash
garmin-claws --agent auth status
```

If tokens are missing:

```bash
garmin-claws auth login --print-instructions
```

Garmin logins are rate-limited from cloud VMs, so the user should run the printed login snippet locally, zip `~/.garminconnect`, transfer it, then run:

```bash
garmin-claws auth import garminconnect-tokens.zip
```

Tokens are read from `~/.garminconnect/garmin_tokens.json` unless `GARMIN_CLAWS_TOKEN_DIR` is set.

## Discoverability

Before using unfamiliar commands, ask the CLI what it supports:

```bash
garmin-claws capabilities --json
garmin-claws schema list --json
garmin-claws schema show daily_summary --json
```

Use this instead of relying on stale docs in prompt context.

## Preferred agent commands

Use normalized JSON output:

```bash
garmin-claws daily summary --date today --json
garmin-claws sleep summary --date yesterday --json
garmin-claws activity recent --limit 10 --json
```

Compatibility aliases also exist:

```bash
garmin-claws today --json
garmin-claws activities --limit 10 --json
```

## Daily brief workflow

First inspect the flow:

```bash
garmin-claws flow plan daily-brief --json
```

Then run the planned commands:

```bash
garmin-claws daily summary --date today --json
garmin-claws sleep summary --date yesterday --json
garmin-claws activity recent --limit 5 --json
```

Summarize:

- sleep duration/quality signals;
- activity volume and notable sessions;
- recovery/readiness signals if present;
- one practical suggestion for the day.

Keep the tone coaching-oriented, non-medical, and low-drama.

## Troubleshooting

- `GARMIN_AUTH_MISSING`: run the auth import flow.
- Garmin 429/login failure: stop retrying from the VM; use local login and token transfer.
- 403/expired token: rerun the local login flow and import a fresh zip.
- Unknown schema/flow: run `garmin-claws schema list --json` or `garmin-claws capabilities --json`.
