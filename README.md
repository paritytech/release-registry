  # Release Registry

  Single source of truth regarding past and future releases of the Polkadot SDK.

  This repo contains a [JSON schema](./releases-v1.schema.json) as schema for the [releases.json](./releases-v1.json) file that tracks all SDK releases. The schema and releases file are suffixed with `v1` in case we ever do a breaking change to the format, then the old format can still be supported.

  ## Calendar

<!-- Do not manually edit this. Run `python3 json-to-md.py` -->

<!-- TEMPLATE BEGIN -->

| Version | Cutoff | Published | End of Life | State |
|---------|--------|-----------|-------------|-------|
| **[stable2407](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407)** | 2024-04-29 | 2024-04-29 | 2025-04-29 | Maintained |
| &nbsp;&nbsp;[stable2407-1](https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-1) | 2024-08-14 | 2024-08-15 |  | Maintained |
| &nbsp;&nbsp;stable2407-2 | 2024-08-28 | ~2024-08-30 |  | Planned |
| &nbsp;&nbsp;stable2407-3 | ~2024-09-11 | ~2024-09-13 |  | Planned |
| **stable2410** | ~2024-09-02 | ~2024-09-25 | ~2025-09-25 | Planned |


<!-- TEMPLATE END -->

Dates with a `~` prefix are estimates.

## Roadmap

  - [ ] Double check dates and make the repo public
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
