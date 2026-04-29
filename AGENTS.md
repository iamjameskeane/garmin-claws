# AGENTS.md

Guidance for coding agents working on `garmin-claws`.

## North star

`garmin-claws` is not mainly a human Garmin CLI. It is a stable, low-context Garmin data API for agents, exposed as a CLI.

Optimize for:

1. deterministic behavior;
2. stable JSON contracts;
3. structured errors;
4. no prompts in agent mode;
5. small normalized outputs by default;
6. runtime introspection via `capabilities` and `schema`.

## Development loop

Use TDD for behavior changes:

```bash
python -m pytest tests/test_cli.py::test_name -q
python -m pytest -q
```

Install locally:

```bash
pip install -e '.[dev]'
```

## CLI contract

- `--json` commands emit response envelopes to stdout.
- `--agent` forces structured error envelopes.
- Human diagnostics go to stderr.
- Do not print token contents.
- Prefer normalized commands over exposing raw Garmin API blobs.

## Preferred command taxonomy

- `auth ...` for token lifecycle.
- `daily summary` for daily normalized metrics.
- `sleep summary` for sleep normalized metrics.
- `activity recent` for recent normalized activity summaries.
- `flow plan <name>` for planning agent workflows without side effects.
- `schema ...` and `capabilities` for introspection.

## Adding commands

When adding a new agent-facing command:

1. Add tests first.
2. Return a stable envelope: `ok`, `schema_version`, `data`, `warnings`, `meta`.
3. Add/update a schema in `schemas/` and embedded runtime `SCHEMAS` if needed.
4. Add the command to `CAPABILITIES` if agents should discover it.
5. Update `skills/garmin-claws/SKILL.md` if it changes the recommended agent workflow.
6. Run `pytest -q` before committing.

## Git identity

Use:

```bash
git config user.name "Clawsaurusrex"
git config user.email "clawsaurusrex@agentmail.to"
```
