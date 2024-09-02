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
| &nbsp;&nbsp;stable2407-3 | ~2024-10-07 | ~2024-10-10 |  | Planned |
| &nbsp;&nbsp;stable2407-4 | ~2024-11-04 | ~2024-11-07 |  | Planned |
| &nbsp;&nbsp;stable2407-5 | ~2024-12-02 | ~2024-12-05 |  | Planned |
| &nbsp;&nbsp;stable2407-6 | ~2025-01-06 | ~2025-01-09 |  | Planned |
| &nbsp;&nbsp;stable2407-7 | ~2025-02-03 | ~2025-02-06 |  | Planned |
| &nbsp;&nbsp;stable2407-8 | ~2025-03-03 | ~2025-03-06 |  | Planned |
| &nbsp;&nbsp;stable2407-9 | ~2025-04-07 | ~2025-04-10 |  | Planned |
| &nbsp;&nbsp;stable2407-10 | ~2025-05-05 | ~2025-05-08 |  | Planned |
| **stable2409** | ~2024-09-02 | ~2024-09-25 | ~2025-09-25 | Planned |
| &nbsp;&nbsp;stable2409-1 | ~2024-10-14 | ~2024-10-17 |  | Planned |
| &nbsp;&nbsp;stable2409-2 | ~2024-11-11 | ~2024-11-14 |  | Planned |
| &nbsp;&nbsp;stable2409-3 | ~2024-12-09 | ~2024-12-12 |  | Planned |
| &nbsp;&nbsp;stable2409-4 | ~2025-01-13 | ~2025-01-16 |  | Planned |
| &nbsp;&nbsp;stable2409-5 | ~2025-02-10 | ~2025-02-13 |  | Planned |
| &nbsp;&nbsp;stable2409-6 | ~2025-03-10 | ~2025-03-13 |  | Planned |
| &nbsp;&nbsp;stable2409-7 | ~2025-04-14 | ~2025-04-17 |  | Planned |
| &nbsp;&nbsp;stable2409-8 | ~2025-05-12 | ~2025-05-15 |  | Planned |
| &nbsp;&nbsp;stable2409-9 | ~2025-06-09 | ~2025-06-12 |  | Planned |
| &nbsp;&nbsp;stable2409-10 | ~2025-07-14 | ~2025-07-17 |  | Planned |
| &nbsp;&nbsp;stable2409-11 | ~2025-08-11 | ~2025-08-14 |  | Planned |
| &nbsp;&nbsp;stable2409-12 | ~2025-09-08 | ~2025-09-11 |  | Planned |
| &nbsp;&nbsp;stable2409-13 | ~2025-10-13 | ~2025-10-16 |  | Planned |
| **stable2412** | ~2024-11-06 | ~2024-12-16 | ~2025-12-16 | Planned |
| &nbsp;&nbsp;stable2412-1 | ~2025-01-20 | ~2025-01-23 |  | Planned |
| &nbsp;&nbsp;stable2412-2 | ~2025-02-17 | ~2025-02-20 |  | Planned |
| &nbsp;&nbsp;stable2412-3 | ~2025-03-17 | ~2025-03-20 |  | Planned |
| &nbsp;&nbsp;stable2412-4 | ~2025-04-21 | ~2025-04-24 |  | Planned |
| &nbsp;&nbsp;stable2412-5 | ~2025-05-19 | ~2025-05-22 |  | Planned |
| &nbsp;&nbsp;stable2412-6 | ~2025-06-16 | ~2025-06-19 |  | Planned |
| &nbsp;&nbsp;stable2412-7 | ~2025-07-21 | ~2025-07-24 |  | Planned |
| &nbsp;&nbsp;stable2412-8 | ~2025-08-18 | ~2025-08-21 |  | Planned |
| &nbsp;&nbsp;stable2412-9 | ~2025-09-15 | ~2025-09-18 |  | Planned |
| &nbsp;&nbsp;stable2412-10 | ~2025-10-20 | ~2025-10-23 |  | Planned |
| &nbsp;&nbsp;stable2412-11 | ~2025-11-17 | ~2025-11-20 |  | Planned |
| &nbsp;&nbsp;stable2412-12 | ~2025-12-15 | ~2025-12-18 |  | Planned |


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
