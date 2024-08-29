# Release Registry

Single source of truth regarding past and future releases of the Polkadot SDK.

This repo contains a [JSON schema](./releases-v1.schema.json) as schema for the [releases.json](./releases-v1.json) file that tracks all SDK releases. The schema and releases file are suffixed with `v1` in case we ever do a breaking change to the format, then the old format can still be supported.

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
