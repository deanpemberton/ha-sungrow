# Sungrow Local

A native, read-only Home Assistant integration for Sungrow SG5K-D local telemetry.
It talks directly to the inverter/dongle on the LAN and can expose the same
snapshot as Home Assistant entities and retained MQTT JSON.

## Status

Live hardware validated against the SG5K-D during development. The transport
uses Sungrow's encrypted Modbus envelope and the vendor default transport key
used by the historical `SungrowModbusTcpClient` library. That key is a protocol
constant, not an installation credential.

The integration remains read-only: it issues input-register reads only and
provides no inverter control services.

## Polling and inverter safety

The SG5K-D can become unstable when polled too aggressively, so polling is
deliberately conservative:

- Default polling: **60 seconds**.
- Minimum configurable polling: **30 seconds**.
- One scheduled poll produces one shared snapshot for HA and MQTT.
- Two encrypted FC04 block reads are used per poll, matching the historical
  Solariot SG5K-D scan ranges.
- Session-key negotiation is cached for the day instead of repeated every poll.
- Failed reads are not immediately retried in a tight loop; recovery occurs on
  the next scheduled coordinator update.

## Telemetry

The integration exposes the historical Solariot SG5K-D measurements plus useful
diagnostics available in the same register ranges:

- Daily and total generation energy.
- Total and daily run time.
- Inverter temperature.
- MPPT 1 and MPPT 2 voltage, current, and calculated power.
- Total DC power, AC active power, apparent power, and reactive power.
- Phase voltage/current values.
- Grid frequency and power factor.
- Device status and fault code.
- Grid import/export power and house/meter power.
- Daily imported energy.
- Daily and total consumption.
- Nominal active/reactive power.
- Negative voltage-to-ground diagnostic.

MPPT power is calculated as voltage × current from the same snapshot.

## MQTT

If Home Assistant's MQTT integration is loaded, each successful inverter poll
publishes the same snapshot to MQTT. There is no second inverter scrape.

Default topics:

- State: `inverter/stats`
- Availability: `inverter/status`

The retained state JSON contains normalized field names plus legacy Solariot
aliases such as `daily_power_yield`, `total_power_yield`, `internal_temp`,
`pv1_voltage`, `pv1_current`, `total_pv_power`, `total_active_power`,
`export_power`, and `power_meter`.

Each payload also includes `_source` and `_last_update` so consumers can detect
fresh data. The availability topic is retained as `online` / `offline`.

The MQTT state topic and poll interval can be changed in integration options.

## Installation

See [docs/INSTALL.md](docs/INSTALL.md) for the full installation workflow.

For development on Home Assistant OS, keep the repository on the shared config
filesystem and use a relative symlink for `custom_components/sungrow_local` so
the terminal App and Home Assistant Core resolve the same files.

## Development

Python 3.13; CI runs Ruff lint/format checks and Home Assistant integration tests.

```sh
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

Use issue-linked feature/fix branches from `develop` and PRs into `develop`.
See `AGENTS.md` for repository rules.

## Privacy

Installation addresses and optional key overrides remain in Home Assistant's
local config-entry storage. The repository contains only the public Sungrow
protocol transport constant required by the historical encrypted client, not
installation credentials.

## License

MIT.
