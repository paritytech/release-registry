# Release Registry

Single source of truth regarding past and future releases of the Polkadot SDK.

This repo contains a [JSON schema](./releases-v1.schema.json) as schema for the [releases.json](./releases-v1.json) file that tracks all SDK releases.

## Calendar

<!-- DO NOT EDIT. Run `python3 update-readme.py` instead. -->

<!-- TEMPLATE BEGIN -->

| Version | Cutoff | Published | End of Life | State |
|---------|--------|-----------|-------------|-------|
| **stable2407** | &nbsp;&nbsp;2024-04-29 | &nbsp;&nbsp;2024-04-29 | &nbsp;&nbsp;2025-04-29 | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407) |
| &nbsp;&nbsp;stable2407-1 | &nbsp;&nbsp;2024-08-14 | &nbsp;&nbsp;2024-08-15 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-1) |
| &nbsp;&nbsp;stable2407-2 | &nbsp;&nbsp;2024-08-28 | &nbsp;&nbsp;2024-09-02 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-2) |
| &nbsp;&nbsp;stable2407-3 | ~2024-10-07 | ~2024-10-10 |  | Planned |
| &nbsp;&nbsp;stable2407-4 | ~2024-11-04 | ~2024-11-07 |  | Planned |
| &nbsp;&nbsp;stable2407-5 | ~2024-12-02 | ~2024-12-05 |  | Planned |
| &nbsp;&nbsp;stable2407-6 | ~2025-01-06 | ~2025-01-09 |  | Planned |
| &nbsp;&nbsp;(4 more) |  |  | | |
| **stable2409** | &nbsp;&nbsp;2024-09-02 | ~2024-09-25 | ~2025-09-25 | Testing |
| &nbsp;&nbsp;stable2409-1 | ~2024-10-14 | ~2024-10-17 |  | Planned |
| &nbsp;&nbsp;stable2409-2 | ~2024-11-11 | ~2024-11-14 |  | Planned |
| &nbsp;&nbsp;stable2409-3 | ~2024-12-09 | ~2024-12-12 |  | Planned |
| &nbsp;&nbsp;stable2409-4 | ~2025-01-13 | ~2025-01-16 |  | Planned |
| &nbsp;&nbsp;(9 more) |  |  | | |
| **stable2412** | ~2024-11-06 | ~2024-12-16 | ~2025-12-16 | Planned |
| &nbsp;&nbsp;stable2412-1 | ~2025-01-20 | ~2025-01-23 |  | Planned |
| &nbsp;&nbsp;stable2412-2 | ~2025-02-17 | ~2025-02-20 |  | Planned |
| &nbsp;&nbsp;stable2412-3 | ~2025-03-17 | ~2025-03-20 |  | Planned |
| &nbsp;&nbsp;stable2412-4 | ~2025-04-21 | ~2025-04-24 |  | Planned |
| &nbsp;&nbsp;(8 more) |  |  | | |


<!-- TEMPLATE END -->

Dates with `~` are estimates.

### Subscribe

Subscribe to the calendar by adding this iCal link to your Google or Apple calendar:

`https://raw.githubusercontent.com/paritytech/release-registry/main/releases-v1.ics`

 Google has an "From URL" and Apple "New Calendar Subscription" option for this:

<!-- two pics next to each other -->

 Google            |  Apple
:-------------------------:|:-------------------------:
![](.assets/screenshot-google-cal.png)  |  ![](.assets/screenshot-apple-cal.png)

## Goals

The two main goals of this repo are to improve:
- **Communication**: clear information about past and upcoming releases. Hoarding information inside Parity is not helpful. This repo aims to make it easier for the Polkadot Ecosystem to know what's going on.
- **Expectations**: set clear expectations by having a public schedule. Know when what is coming.

## Schedule

The Polkadot SDK has a `stableYYMMDD` release every 3 months. Each stable release is supported for one year through a monthly patching schedule.  
As there can be four stable releases in parallel, the patching schedule is aligned with the weeks of a month. Each stable release is assigned a week in which on Monday its patch will be cut off and on Thursday it will be published.

![Monthly Patching](./.assets/monthly-patching.png)

Stable releases undergo a 1.5 month QA period before being published. This explains the difference between the `cutoff` and `published` dates below.

## Maintenance

### Release Planning
(how to add a new release to the json)

First, check the calendar when about 3 months passed from the publish date of the last release. Then subtract about 1.5 months from that and call the plan command with that date:

```bash
python3 manage.py release plan stable2412 2024-11-06
```

Then figure out when the first patch date should be; you have to select a Monday for the patching schedule to be calculated (errors if not a Monday). You should select either a week that is empty and has no schedule, or the one where the oldest release is currently being patched.  
The script will then count the how many-th monday of the month it is and begin lining it up with the months like in the image above.

Example where we want the first patch to be cut off on 24024-07-29:

```bash
python3 manage.py backfill-patches stable2407 --start-date 2024-07-29
```

Then update the README to see the changes by running `just`.

### Release Cutoff / Publish

Run this command to cut off a release:

```bash
python3 manage.py release cutoff stable2407-2 2024-09-02
```

With `publish` likewise.

## Automation

Two scripts are currently in place to:

- [manage.py](./manage.py) - manage the releases json file (plan, cutoff, publish, etc)
- [update-readme.py](./update-readme.py) - updates the README.md file with the data from the releases.json file
- [update-calendar.py](./update-calendar.py) - generates an iCal file from the releases.json file

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
