# Local Solar Inverter

A native, read-only Home Assistant integration for local solar inverter telemetry.\nIt currently supports Sungrow SG5K-D hardware and includes a pre-hardware GoodWe\nMS G3 driver targeting GW8500-MS-30. One shared poll snapshot feeds both Home\nAssistant entities and retained MQTT JSON.

## Status\n\nLive hardware validated against the SG5K-D during development. GoodWe MS G3\nsupport is implemented against the same `goodwe==0.4.10` protocol library pinned\nby current Home Assistant Core and awaits final validation on the purchased\nGW8500-MS-30.\n\nThe GoodWe driver supports local UDP/8899 and Modbus TCP/502, auto-detects the\nworking path once during setup, caches it, and exposes all runtime sensors reported\nby the upstream MS-family driver, including the third MPPT and optional meter data.\n\n The transport
uses Sungrow's encrypted Modbus envelope and the vendor default transport key
used by the historical `SungrowModbusTcpClient` library. That key is a protocol
constant, not an installation credential.

The integration remains read-only. No inverter control or GoodWe settings writes\nare exposed.

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

## GoodWe MS G3 commissioning

For GW8500-MS-30 the integration expects three MPPTs and attempts local connectivity
through the mature GoodWe protocol stack. Choose **Auto** first; setup tries UDP 8899
then Modbus TCP 502 and remembers the successful path. If Modbus TCP is used, it must
be enabled on the installed communication dongle/firmware.

Arrival-day validation is intentionally small:

1. Add a second Local Solar Inverter entry and choose **GoodWe**.
2. Enter the inverter/dongle LAN address and leave transport on **Auto**.
3. Confirm model detection and MPPT 1/2/3 voltage, current and power against SolarGo.
4. Confirm total DC power, AC output power, temperature, daily/total generation and
   optional smart-meter import/export/house-load values.
5. Identify which physical roof string corresponds to MPPT 1/2/3 and label dashboards.
6. If connectivity differs from expected, capture sanitized diagnostics and adjust only
   the model/transport quirk rather than changing the shared HA layer.
