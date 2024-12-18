# Release Registry

Single source of truth regarding past and future releases of the Polkadot SDK.

This repo contains a [releases-v1.json](./releases-v1.json) file that tracks all SDK releases and a [JSON schema](./releases-v1.schema.json) to ensure that it is in canonical format.

## Calendar

<!-- DO NOT EDIT. Run `python3 update-readme.py` instead. -->

<!-- TEMPLATE BEGIN -->

| Version | Cutoff | Published | End of Life | State |
|---------|--------|-----------|-------------|-------|
| **stable2407** | &nbsp;&nbsp;2024-04-29 | &nbsp;&nbsp;2024-04-29 | &nbsp;&nbsp;2025-04-29 | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407) |
| &nbsp;&nbsp;stable2407-1 | &nbsp;&nbsp;2024-08-14 | &nbsp;&nbsp;2024-08-15 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-1) |
| &nbsp;&nbsp;stable2407-2 | &nbsp;&nbsp;2024-08-28 | &nbsp;&nbsp;2024-09-02 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-2) |
| &nbsp;&nbsp;stable2407-3 | &nbsp;&nbsp;2024-10-10 | &nbsp;&nbsp;2024-10-10 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-3) |
| &nbsp;&nbsp;stable2407-4 | &nbsp;&nbsp;2024-11-11 | &nbsp;&nbsp;2024-11-11 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-4) |
| &nbsp;&nbsp;stable2407-5 | &nbsp;&nbsp;2024-12-02 | &nbsp;&nbsp;2024-12-09 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-5) |
| &nbsp;&nbsp;stable2407-6 | ~2025-01-06 | ~2025-01-09 |  | Planned |
| &nbsp;&nbsp;stable2407-7 | ~2025-02-03 | ~2025-02-06 |  | Planned |
| &nbsp;&nbsp;stable2407-8 | ~2025-03-03 | ~2025-03-06 |  | Planned |
| &nbsp;&nbsp;(2 more) |  |  | | |
| **stable2409** | &nbsp;&nbsp;2024-09-02 | &nbsp;&nbsp;2024-09-26 | ~2025-09-25 | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2409) |
| &nbsp;&nbsp;stable2409-1 | &nbsp;&nbsp;2024-10-21 | &nbsp;&nbsp;2024-10-21 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2409-1) |
| &nbsp;&nbsp;stable2409-2 | &nbsp;&nbsp;2024-11-14 | &nbsp;&nbsp;2024-11-14 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2409-2) |
| &nbsp;&nbsp;stable2409-3 | ~2024-12-09 | ~2024-12-12 |  | Planned |
| &nbsp;&nbsp;stable2409-4 | ~2025-01-13 | ~2025-01-16 |  | Planned |
| &nbsp;&nbsp;stable2409-5 | ~2025-02-10 | ~2025-02-13 |  | Planned |
| &nbsp;&nbsp;(8 more) |  |  | | |
| **stable2412** | ~2024-11-06 | ~2024-12-16 | ~2025-12-16 | Planned |
| &nbsp;&nbsp;stable2412-1 | ~2025-01-20 | ~2025-01-23 |  | Planned |
| &nbsp;&nbsp;stable2412-2 | ~2025-02-17 | ~2025-02-20 |  | Planned |
| &nbsp;&nbsp;stable2412-3 | ~2025-03-17 | ~2025-03-20 |  | Planned |
| &nbsp;&nbsp;(9 more) |  |  | | |
| **stable2503** | ~2025-02-17 | ~2025-03-31 | ~2026-03-31 | Planned |
| &nbsp;&nbsp;stable2503-1 | ~2025-04-28 | ~2025-05-01 |  | Planned |
| &nbsp;&nbsp;stable2503-2 | ~2025-05-26 | ~2025-05-29 |  | Planned |
| &nbsp;&nbsp;stable2503-3 | ~2025-06-23 | ~2025-06-26 |  | Planned |
| &nbsp;&nbsp;(10 more) |  |  | | |

<!-- TEMPLATE END -->

Dates with `~` are estimates.

### Subscribe

Subscribe to the calendar by adding this iCal link to your Google or Apple calendar:

`https://raw.githubusercontent.com/paritytech/release-registry/main/releases-v1.ics`

 Google has an "From URL" and Apple "New Calendar Subscription" option for this:

 Google            |  Apple
:-------------------------:|:-------------------------:
![](.assets/screenshot-google-cal.png)  |  ![](.assets/screenshot-apple-cal.png)

## Schedule

### Releases

The Polkadot SDK has a `stableYYMMDD` release every 3 months. Each stable release is supported for one year through a monthly patching schedule. The releases are not *exactly* 3 months apart, but we try to keep it close. The exact dates are in the calendar.  
Stable releases undergo a 1.5 month QA period before being published. This explains the difference between the `cutoff` and `published` dates.

### Patches

The patching schedule of each stable release is assigned a week of the month. This works well, since there can be at most four stable releases maintained at once.  For example: release `stable2407` is always patched in the first week of a month. This means that on the first Monday of each month, a new patch is cut off, and on the first Thursday after that Monday, it is published.

![Monthly Patching](./.assets/monthly-patching.png)

## Goals

The two main goals of this repo are to improve:
- **Communication**: clear information about past and upcoming releases. Hoarding information inside Parity is not helpful. This repo aims to make it easier for the Polkadot Ecosystem to know what's going on. This can be helpful to all departments; developers, marketing, devops, security etc.
- **Expectations**: set clear expectations by having a public schedule. Know when what is coming.

## Maintenance


### Release Planning
(how to add a new release to the json)

First, check the calendar when about 3 months passed from the publish date of the last release. Then subtract about 1.5 months from that and call the plan command with that date:

```bash
python3 scripts/manage.py release plan stable2412 2024-11-06
```

Then figure out when the first patch date should be; you have to select a Monday for the patching schedule to be calculated (errors if not a Monday). You should select either a week that is empty and has no schedule, or the one where the oldest release is currently being patched.  
The script will then count the how many-th monday of the month it is and begin lining it up with the months like in the image above.

Example where we want the first patch to be cut off on 24024-07-29:

```bash
python3 scripts/manage.py backfill-patches stable2407 --start-date 2024-07-29
```

Then update the README to see the changes by running `just`.

### Release Cutoff / Publish

Run this command to cut off a release:

```bash
python3 scripts/manage.py release cutoff stable2407-2 2024-09-02
```

With `publish` likewise.

## Automation

Two scripts are currently in place to:

- [manage.py](./scripts/manage.py) - manage the releases json file (plan, cutoff, publish, etc)
- [update-readme.py](./scripts/update-readme.py) - updates the README.md file with the data from the releases.json file
- [update-calendar.py](./scripts/update-calendar.py) - generates an iCal file from the releases.json file
- [update-badges.py](./scripts/update-badges.py) - re-generate the badges in the `badges` folder for downstream use.

## Roadmap

  - [x] Double check dates and make the repo public
  - [ ] Sync with other teams on how to incooperate this
    - [ ] Release Engineering
    - [ ] Security
    - [ ] DevOps
    - [ ] Marketing
    - [ ] CEX Comms
    - [ ] Fellowship Secretary
  - [ ] Setup Gh pages with calendar
  - [ ] Setup automation to keep data in sync
  - [ ] Setup feed to subscribe on changes
