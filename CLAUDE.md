# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The single source of truth for Polkadot SDK release schedules. The authoritative data is `releases-v1.json`, validated against `releases-v1.schema.json`. Every other tracked artifact (`README.md` table, `CALENDAR.md`, `releases-v1.ics`, `badges/*.svg`, `.assets/timeline-gantt.png`) is generated from that JSON — never edit them by hand.

## Common commands

All Python scripts run inside the local `venv/` (created on first `just` invocation from `scripts/requirements.txt`).

Regenerate every derived artifact (README table, CALENDAR.md, ICS, badges, Gantt PNG):
```bash
just            # equivalent to: just venv readme calendar badges gantt
```

Individual targets: `just readme`, `just calendar`, `just badges`, `just gantt`.

Mutate `releases-v1.json` via `scripts/manage.py` (also wrapped by Justfile recipes):
```bash
just plan stable2412 2024-11-06 1.17.0   # plan a new stable, semver optional
just cutoff stable2407-2 2024-09-02      # mark a release/patch cut off
just publish stable2407-2 2024-09-05     # mark released
just deprecate stable2407 2025-04-29 stable2503
just backfill stable2407 2024-07-29      # generate 13 planned patches; date MUST be a Monday
```

After any data change, run `just` to refresh derived files — CI fails the PR otherwise (see `.github/workflows/update-files.yml`).

## Architecture

**Data model** (`releases-v1.schema.json`):
- Top-level keys are projects: `"Polkadot SDK"` and `"Fellowship Runtimes"`.
- Each project has `recommended`, `changelog` (URL with `$TAG` placeholder), and `releases[]`.
- A `release` is a `stableYYMM` entry with `cutoff`, `publish`, `endOfLife`, `state`, and a `patches[]` list.
- A `patch` is `stableYYMM-N` (N ≥ 1, no zero padding).
- Date fields are either an exact `{when, tag}` / ISO date string, or `{estimated: "YYYY-MM-DD"}`. Code that reads dates must handle both shapes — see `format_date` in `scripts/update-readme.py`.
- `state` is one of `planned | staging | released | skipped`, or an object `{deprecated: {since, useInstead}}`. Same dual-shape pattern.

**Patching cadence** (encoded in `manage.py`):
- Stable releases publish ~1.5 months after cutoff (`update_release` adds 45 days, bumps to Monday if the publish date lands on a weekend).
- `endOfLife` defaults to publish + 365 days.
- `backfill-patches` requires a Monday start date and lays out 13 monthly patches by computing the "Nth Monday of the month" once and reusing that ordinal each subsequent month (`get_nth_monday` / `next_nth_monday`). Cutoff Monday → publish Thursday (cutoff + 3 days).
- `deprecate` marks the release deprecated, converts already-`released` patches to deprecated, and flips remaining `planned` patches to `skipped`.

**Generators** (all read `releases-v1.json`, all idempotent):
- `scripts/update-readme.py` — rewrites the table between `<!-- TEMPLATE BEGIN -->` / `<!-- TEMPLATE END -->` markers in `README.md`. With `--max-patches 99 --output CALENDAR.md` it produces the full calendar.
- `scripts/update-calendar.py` — emits `releases-v1.ics`.
- `scripts/update-badges.py` — writes SVGs into `badges/` (current/next stable).
- `scripts/update-gantt.py` — renders `.assets/timeline-gantt.png` (matplotlib + pandas + plotly stack; `weasyprint`/`pillow` pulled in by the larger toolchain).

## Conventions when editing

- `releases-v1.json` is the only file you should hand-edit for release data. Prefer running the `manage.py` / `just` commands over editing JSON directly so validation and patch-generation stay consistent.
- The README table between the template markers is auto-generated. If you need to change the prose, edit outside the markers; if you need to change table formatting, edit `update-readme.py`.
- Version regex enforced by `validate_version`: `^stable2[0-9][01][0-9](-[0-9]*)?$`. The schema is stricter (`stable2[456][01][0-9]`).
- CI runs `just` and diffs everything except `.assets/timeline-gantt.png`; that PNG is intentionally excluded from the change check, so don't gate logic on it.
