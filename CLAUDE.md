# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The single source of truth for Polkadot SDK release schedules. The authoritative data is `releases-v1.json`, validated against `releases-v1.schema.json`. Every other tracked artifact (`README.md` table, `CALENDAR.md`, `releases-v1.ics`, `badges/*.svg`, `.assets/timeline-gantt.png`) is generated from that JSON — never edit them by hand.

## Common commands

The generator scripts, the schema check and the tests run inside the local `venv/`, created from `scripts/requirements.txt` on the first `just` invocation and reinstalled whenever that file changes. `manage.py` only needs the standard library and runs with the system `python3`.

Validate the JSON and regenerate every derived artifact (README table, CALENDAR.md, ICS, badges, Gantt PNG):
```bash
just            # equivalent to: just venv validate readme calendar badges gantt
```

Individual targets: `just validate`, `just readme`, `just calendar`, `just badges`, `just gantt`. `just test` runs the unit tests (`scripts/test_*.py`).

Mutate `releases-v1.json` via `scripts/manage.py` (also wrapped by Justfile recipes):
```bash
just publish stable2611 2026-11-26       # mark a release or patch released; see "Monthly cadence" for what else it does
just plan stable2612 2026-12-14          # plan or move a monthly release; the cutoff date MUST be a Monday
just plan stable2611 2026-11-23 1.26.0   # semver: only for a monthly release that has none before it
just plan stable2611-1 2026-12-03        # announce a single patch
just skip stable2701                     # skip a release or patch
just plan-ahead                          # plan monthly releases until six are planned
just recommend stable2609 2              # set `recommended`; the patch number is optional
just cutoff stable2609-3 2027-01-11      # mark a release/patch cut off (state `staging`); not part of the monthly routine
just deprecate stable2407 2025-04-29 stable2503
just backfill stable2407 2024-07-29      # quarterly only: generate 13 planned patches; date MUST be a Monday
```

A quarterly release can only be planned with `manage.py` directly: `python3 scripts/manage.py release plan stable2412 2024-11-06 1.17.0 --cadence quarterly`.

After any data change, run `just` to refresh derived files — CI fails the PR otherwise (see `.github/workflows/update-files.yml`).

## Architecture

**Data model** (`releases-v1.schema.json`):
- Top-level keys are projects: `"Polkadot SDK"` and `"Fellowship Runtimes"`.
- Each project has `recommended`, `changelog` (URL with `$TAG` placeholder), and `releases[]`.
- A `release` is a `stableYYMM` entry with `cutoff`, `publish`, `endOfLife`, `state`, and an optional `patches[]` list.
- `cadence` is `"monthly"` for the releases from `stable2611` on. A release without the field is a legacy quarterly release; test it with `registry.is_monthly`. The boolean `lts` is reserved for long-term support releases and not set by any command yet; `manage.py` leaves the end of life of such a release alone and does not deprecate it.
- A `patch` is `stableYYMM-N` (N ≥ 1, no zero padding).
- Date fields are either an exact `{when, tag}` / ISO date string, or `{estimated: "YYYY-MM-DD"}`. Code that reads dates must handle both shapes — see `date_of` in `scripts/registry.py` and `format_date` in `scripts/update-readme.py`.
- `state` is one of `planned | staging | released | skipped`, or an object `{deprecated: {since, useInstead}}`. Same dual-shape pattern. Never write another state: `paritytech/deployment-tracker` parses this file and rejects anything else. Fields it does not know are fine.

**Monthly cadence** (encoded in `manage.py`):
- Week rule: the cutoff is the last Monday whose Friday is in the same month (`last_full_week_monday`), publish is that Thursday (cutoff + 3 days). `plan` rejects a cutoff that is not a Monday.
- `sync_monthly_chain` runs before every save and re-derives two things for the monthly releases, in name order and ignoring skipped ones: `endOfLife` is the publish date of the next release (from the week rule if none is planned), and the semver of each `planned` release is the minor version of the one before it plus one. Releases in other states keep their semver, so the one recorded at publish is what the planned ones follow. It also gives every patch of a monthly release the major and minor version of its release.
- `publish` of a monthly release also deprecates the earlier released monthly releases (their `endOfLife` becomes the publish date), runs `plan_ahead` so that six stay planned, and moves `recommended` if it pointed at a release it deprecated. It refuses to run while an earlier monthly release is `planned` or `staging`. An explicit semver is recorded; publishing again with another date corrects the date and the deprecation it caused.
- `plan` takes a semver only to confirm the derived one, or to set it for a monthly release with none before it. `skip` removes the semver, so the planned releases after it move down by one.
- A monthly release cannot join the schedule (new, or planned again after a skip) behind one that is already cut off or released (`check_not_overtaken`).
- Monthly releases have no patch schedule: `backfill-patches` rejects them. A patch is added with `plan` or `publish` of `stableYYMM-N` and gets its semver from the release.

**Guards for both cadences** (in `manage.py`; they exist because the workflows pass free-text names):
- `RELEASE_ACTIONS` lists the states in which a release accepts each action: a released or deprecated one can no longer be planned, cut off or skipped, and one that is cut off can no longer be planned. Publishing a released one again is allowed, to correct the date.
- A patch can only be cut off or published once its release is released (or deprecated); planning one is always possible.
- `remove`, `remove-patches`, `deprecate` and `recommend` take a release and reject the name of a patch.
- An unknown release or patch, like every other rejected input, ends with `Error: ...` and exit status 1, and leaves the file untouched.

**Quarterly cadence** (legacy, the releases up to `stable2609`):
- Stable releases publish ~1.5 months after cutoff (`new_quarterly_release` adds 45 days, bumps to Monday if the publish date lands on a weekend).
- `endOfLife` defaults to publish + 365 days.
- `backfill-patches` requires a Monday start date and lays out 13 monthly patches by computing the "Nth Monday of the month" once and reusing that ordinal each subsequent month (`get_nth_monday` / `next_nth_monday`). Cutoff Monday → publish Thursday (cutoff + 3 days).
- `deprecate` marks the release deprecated, converts already-`released` patches to deprecated, and flips the remaining `planned` and `staging` patches to `skipped`. The publish of a monthly release does the same to the monthly release it replaces.

**Scripts** (all read `releases-v1.json`; the generators are idempotent):
- `scripts/registry.py` — helpers shared by `manage.py` and the generators (`is_monthly`, `release_sort_key`, `date_of`). The generators have a hyphen in their file name and cannot import from each other.
- `scripts/validate.py` — checks the JSON against the schema, including the `date` format.
- `scripts/update-readme.py` — rewrites the table between `<!-- TEMPLATE BEGIN -->` / `<!-- TEMPLATE END -->` markers in `README.md`. With `--max-patches 99 --output CALENDAR.md` it produces the full calendar.
- `scripts/update-calendar.py` — emits `releases-v1.ics`.
- `scripts/update-badges.py` — writes SVGs into `badges/` (recommended release, and the planned release that is published next).
- `scripts/update-gantt.py` — renders `.assets/timeline-gantt.png` (matplotlib + pandas + plotly stack; `weasyprint`/`pillow` pulled in by the larger toolchain). Two panels on one time axis: the monthly releases as one row of segments (publish date to end of life, deprecated ones included, patches as markers below), and the supported quarterly releases as one row per release and patch. Skipped releases are left out, and a panel with nothing to show is dropped. After changing it, look at the image: the tests only check its data and that it draws.
- `scripts/test_manage.py`, `scripts/test_validate.py`, `scripts/test_gantt.py` — unit tests (stdlib `unittest`). The first drives `manage.py` through its command line on a temporary file. Extend them when changing `manage.py`, the schema or the chart.

## Conventions when editing

- `releases-v1.json` is the only file you should hand-edit for release data. Prefer running the `manage.py` / `just` commands over editing JSON directly so validation, the derived monthly fields and patch-generation stay consistent.
- The README table between the template markers is auto-generated. If you need to change the prose, edit outside the markers; if you need to change table formatting, edit `update-readme.py`.
- Version regex enforced by `validate_version`: `stable2[0-9](0[1-9]|1[0-2])(-[1-9][0-9]*)?`. The schema limits the year to `stable2[4-9]`.
- CI runs `just test` and `just`, then fails on any change or untracked file except `.assets/timeline-gantt.png`; that PNG is intentionally excluded from the change check, so don't gate logic on it. Scripts must not leave files behind (`__pycache__/` is ignored).
- The four manual workflows (new, plan, skip, deprecate release) only collect inputs and call the reusable `.github/workflows/reusable-release-pr.yml`, which runs the `just` recipes, regenerates files, commits, pushes and opens the PR. Commits are signed as ParityReleases with the release team's KMS-held GPG key via pgpkms (secrets from the `release` environment, same mechanism as polkadot-sdk) because the paritytech org ruleset on `main` blocks merging PRs with unsigned commits and auto-merge cannot bypass it. New workflows that commit should go through `reusable-release-pr.yml`; human commits must be signed too. Both it and the PR check install the toolchain via `.github/actions/setup-toolchain` so they regenerate files identically.
