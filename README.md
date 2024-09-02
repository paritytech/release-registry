  # Release Registry

  Single source of truth regarding past and future releases of the Polkadot SDK.

  This repo contains a [JSON schema](./releases-v1.schema.json) as schema for the [releases.json](./releases-v1.json) file that tracks all SDK releases. The schema and releases file are suffixed with `v1` in case we ever do a breaking change to the format, then the old format can still be supported.

  ## Calendar

<!-- DO NOT EDIT. Run `python3 update-readme.py` instead. -->

<!-- TEMPLATE BEGIN -->

| Version | Cutoff | Published | End of Life | State |
|---------|--------|-----------|-------------|-------|
| **stable2407** | &nbsp;&nbsp;2024-04-29 | &nbsp;&nbsp;2024-04-29 | &nbsp;&nbsp;2025-04-29 | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407) |
| &nbsp;&nbsp;stable2407-1 | &nbsp;&nbsp;2024-08-14 | &nbsp;&nbsp;2024-08-15 |  | [Released](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-1) |
| &nbsp;&nbsp;stable2407-2 | &nbsp;&nbsp;2024-08-28 | ~2024-09-02 |  | Planned |
| &nbsp;&nbsp;stable2407-3 | ~2024-09-11 | ~2024-09-16 |  | Planned |
| &nbsp;&nbsp;stable2407-4 | ~2024-09-25 | ~2024-09-28 |  | Planned |
| &nbsp;&nbsp;(16 more) |  |  | | |
| **stable2409** | ~2024-09-02 | ~2024-09-25 | ~2025-09-25 | Planned |
| &nbsp;&nbsp;stable2409-1 | ~2024-10-09 | ~2024-10-12 |  | Planned |
| &nbsp;&nbsp;stable2409-2 | ~2024-10-23 | ~2024-10-26 |  | Planned |
| &nbsp;&nbsp;stable2409-3 | ~2024-11-06 | ~2024-11-09 |  | Planned |
| &nbsp;&nbsp;(23 more) |  |  | | |
| **stable2501** | ~2024-12-02 | ~2025-01-16 | ~2026-01-16 | Planned |
| &nbsp;&nbsp;stable2501-1 | ~2025-01-30 | ~2025-02-03 |  | Planned |
| &nbsp;&nbsp;stable2501-2 | ~2025-02-13 | ~2025-02-17 |  | Planned |
| &nbsp;&nbsp;stable2501-3 | ~2025-02-27 | ~2025-03-03 |  | Planned |
| &nbsp;&nbsp;(23 more) |  |  | | |


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
