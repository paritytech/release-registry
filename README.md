# Release Registry

Single source of truth regarding past and future releases of the Polkadot SDK.

This repo contains a [JSON schema](./releases-v1.schema.json) as schema for the [releases.json](./releases-v1.json) file that tracks all SDK releases. The schema and releases file are suffixed with `v1` in case we ever do a breaking change to the format, then the old format can still be supported.

## Calendar

<!-- TEMPLATE BEGIN -->

| Version | Cutoff | Published | End of Life | State |
|---------|--------|-----------|-------------|-------|
| <span style='color:white'>**<a href='https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407' style='color: white; text-decoration: underline;text-decoration-style: dotted;'>stable2407</a>**</span> | <span style='color:white'>2024-04-29</span> | <span style='color:white'>2024-04-29</span> | <span style='color:white'>2025-04-29</span> | Maintained |
| <span style='color:green'>&nbsp;&nbsp;<a href='https://github.com/paritytech/polkadot-sdk/releases/tag/polkadot-stable2407-1' style='color: green; text-decoration: underline;text-decoration-style: dotted;'>stable2407-1</a></span> | <span style='color:green'>2024-08-14</span> | <span style='color:green'>2024-08-15</span> | <span style='color:green'></span> |  |
| <span style='color:gray'>&nbsp;&nbsp;stable2407-2</span> | <span style='color:gray'>2024-08-28</span> | <span style='color:gray'>2024-08-30</span> | <span style='color:gray'></span> |  |
| <span style='color:gray'>&nbsp;&nbsp;stable2407-3</span> | <span style='color:gray'>2024-09-11</span> | <span style='color:gray'>2024-09-13</span> | <span style='color:gray'></span> |  |
| <span style='color:gray'>**stable2410**</span> | <span style='color:gray'>2024-09-02</span> | <span style='color:gray'>2024-09-25</span> | <span style='color:gray'>2025-09-25</span> | <span style='color:gray'>Planned</span> |


<!-- TEMPLATE END -->

### Legend

<span style='color:green'>Green</span> - Safe and recommended version.  
<span style='color:orange'>Patched</span> - Some patches were applied to this version. Please update to the latest patch.  
<span style='color:red'>Outdated</span> - Not safe to use, no longer maintained.  
<span style='color:gray'>Planned</span> - Not yet released. All dates are estimates.

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
