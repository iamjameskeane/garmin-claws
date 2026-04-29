---
name: garmin-claws
description: Agent-ready Garmin Connect CLI. Use for fetching Garmin daily stats, sleep, activities, and planning safe health/fitness briefing flows via stable JSON commands.
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

## Auth

Check auth:

```bash
garmin-claws auth status
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

## Agent commands

Use JSON output for agent parsing:

```bash
garmin-claws today --json
garmin-claws sleep YYYY-MM-DD --json
garmin-claws activities --limit 10 --json
```

Plan a named flow without hitting Garmin:

```bash
garmin-claws flow plan daily-brief --json
```

## Daily brief workflow

1. Run `garmin-claws today --json`.
2. Run `garmin-claws sleep $(date -I -d yesterday) --json`.
3. Run `garmin-claws activities --limit 5 --json`.
4. Summarize:
   - sleep duration/quality signals;
   - activity volume and notable sessions;
   - recovery/readiness signals if present;
   - one practical suggestion for the day.

Keep the tone coaching-oriented, non-medical, and low-drama.

## Troubleshooting

- `token file not found`: run the auth import flow.
- Garmin 429/login failure: stop retrying from the VM; use local login and token transfer.
- 403/expired token: rerun the local login flow and import a fresh zip.
