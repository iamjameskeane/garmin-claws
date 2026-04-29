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
  - training readiness
  - HRV
  - body battery
  - calorie burn
---

# garmin-claws

Use `garmin-claws` when the user wants an agent to inspect Garmin Connect data or run a named Garmin-oriented flow.

## When This Skill Activates

- User asks about their Garmin data (sleep, activity, calories, training)
- User wants a fitness/health brief or coaching recommendation
- User asks about training readiness, HRV, or recovery
- Agent needs health context for nutrition or workout decisions

## Quick Reference

```bash
# Daily data
garmin-claws daily summary --date today --json
garmin-claws sleep summary --date yesterday --json
garmin-claws sleep recovery --date today --json
garmin-claws health status --date today --json

# Training
garmin-claws training readiness --date today --json
garmin-claws training load-balance --date today --json
garmin-claws activity recent --limit 10 --json

# Calorie data (for lobster-roll integration)
garmin-claws flow run calories --json

# Composite flows
garmin-claws flow run trainability --date today --json
garmin-claws flow run daily-coach --date today --json

# Introspection
garmin-claws capabilities --json
garmin-claws schema list --json
garmin-claws schema show daily_summary --json
garmin-claws metrics list --json
garmin-claws metrics explain training_readiness --json
```

## Safety Boundaries

- Do not make medical claims or diagnoses
- Treat Garmin data as user-owned private health-adjacent data
- Prefer concise summaries with uncertainty: sleep, activity, load, recovery signals
- Do not print OAuth tokens or token file contents
- If auth is missing, explain the local-machine token transfer flow
- Prefer normalized commands over raw Garmin API responses

## Agent Mode Contract

For automation, prefer:

```bash
garmin-claws --agent <command>
```

or pass `--json` on individual commands. In agent mode:

- no prompts are attempted
- JSON is emitted to stdout
- failures use `garmin-claws.v1.error` envelopes
- human diagnostics go to stderr
- exit codes are meaningful enough for branching

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

## Calorie Flow

The calorie flow bridges Garmin burn data with lobster-roll consumption data:

```bash
garmin-claws flow run calories --json
```

Returns:
- `current.bmr_kilocalories` — resting calories accumulated so far today
- `current.active_kilocalories` — active calories burned so far
- `current.total_burned` — BMR + active
- `projected.total_kilocalories` — BMR projected to 24h + active
- `net_calorie_goal` — user's Garmin goal (if set)

**Formula:** Projected = (BMR_so_far / hours_elapsed) × 24 + Active

The agent combines this with `lobster-roll summary today --json` to calculate calorie balance. No direct dependency between tools.

## Integration with lobster-roll

garmin-claws tracks what you burn. lobster-roll tracks what you eat. The agent bridges them:

```bash
# What you burn
garmin-claws flow run calories --json

# What you eat
lobster-roll summary today --json

# Agent calculates
budget = projected_burn
consumed = lobster_roll_totals
remaining = budget - consumed
```

No cross-dependency. Both tools are independent.

## Daily Brief Workflow

For most coaching questions, prefer the composite flows:

```bash
garmin-claws flow run trainability --date today --json
garmin-claws flow run daily-coach --date today --json
```

`trainability` answers whether the user can train and the maximum sensible intensity. `daily-coach` combines daily stats, sleep recovery, health status, training readiness, load balance, and a practical recommendation.

For a manual daily brief, first inspect the flow:

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

- sleep duration/quality signals
- activity volume and notable sessions
- recovery/readiness signals if present
- one practical suggestion for the day

Keep the tone coaching-oriented, non-medical, and low-drama.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `GARMIN_AUTH_MISSING` | No token file | Run auth import flow |
| 429/login failure | Rate-limited from VM | Use local login + token transfer |
| 403/expired token | Token stale | Rerun local login + import fresh zip |
| Unknown schema/flow | Wrong command name | Run `capabilities` or `schema list` |
| Health status all `unknown` | No overnight data | Check watch worn overnight |

## Pitfalls

- BMR (`bmrKilocalories`) is accumulated so far today, not full 24h — project it
- Active calories exclude tracked workout calories — they're separate
- Health status requires overnight watch wear — returns `unknown` otherwise
- Training readiness needs several weeks of baseline data
- Garmin API rate-limits aggressively from cloud VMs — use local token transfer
