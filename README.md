# Sungrow Local

A native, read-only Home Assistant custom integration for SG5K-D local telemetry.
Runs inside Home Assistant; no MQTT broker, external container or cloud account.

## Status

Experimental: synthetic protocol tests and Home Assistant lifecycle tests pass.
**No live SG5K-D / WiFi V31 hardware has been validated yet.** Do not replace a
working production telemetry source until live readings have been compared.

Supports plain Modbus TCP and the legacy encrypted Sungrow TCP envelope. Some
older dongles require a web transport instead; that transport is not implemented
in this version. An open TCP port alone does not establish compatibility.

## Sensors

- MPPT 1 and MPPT 2 voltage (V), current (A), and calculated DC power (W).
- Total DC power (W), inverter AC output power (W), temperature (°C), frequency (Hz).

MPPT power is voltage × current, not a separate power meter. DC string power
will differ from AC output because of conversion losses and inverter clipping.
The SG5K-D mapping uses input registers 5008–5036, with zero-based Modbus
addresses 5007–5035 and low-word-first 32-bit power values. This map is based on
the existing Solariot SG5K-D map; exact hardware/firmware behavior needs verification.
Invalid unsigned readings produce unknown values, never fabricated zeros.
Connection failures make sensors unavailable, with automatic recovery on the next poll.
Generation energy counters are deferred until their units and width are verified;
instantaneous power sensors cannot be used as energy counters directly.

## Install for development

1. Check out the feature branch or the reviewed develop branch.
2. Copy `custom_components/sungrow_local` into the HA configuration directory's
   `custom_components` directory. Restart Home Assistant.
3. Settings → Devices & services → Add integration → **Sungrow Local**.
4. Enter the device address locally, TCP port (normally 502), and inverter unit
   ID (normally 1). Leave Protocol key empty for plain Modbus. For a dongle that
   requires encryption, enter its 16-byte protocol key as 32 hexadecimal characters.
   This project intentionally contains no embedded protocol key.
5. Default polling is 30 seconds. Change it under integration options (10–3600 seconds).
   Use Reconfigure to change the address or transport key without replacing sensor IDs.

Home Assistant must be able to reach the device on its local network. Encryption
negotiation uses a separate connection followed by one input-register read per poll.
Requests are bounded by a 10-second timeout. This integration issues no inverter
control or register-write commands.

`hacs.json` is included for eventual HACS custom-repository installation. The first
release still needs hardware validation; no release tag is provided yet. Install
manually from the feature branch for testing rather than expecting a stable release.

## Privacy

Device addresses, keys and unit settings stay in local HA configuration storage.
HA backups may include this configuration; treat them as private. Sensor IDs use
random installation IDs, not addresses or serials. Errors contain no device details.
Never upload configuration storage, credentials, keys, real addresses, identifiers
or unsanitized packet captures to the public repository. All tests use synthetic data.

## Development

Python 3.13; tested against Home Assistant 2026.2.3 via the pinned custom integration
pytest plugin. Newer HA versions require a further compatibility check.

```sh
python -m pip install -r requirements-dev.txt
pytest -q
ruff check .
ruff format --check .
```

Use issue-linked feature/fix branches from `develop` and PRs into `develop`.
Use release branches for `main`, merging back into `develop`. Test first, implement,
then refactor. See `AGENTS.md` for repository rules. CI runs tests and formatting checks.

## License

MIT. This is an independent transport implementation informed by the publicly
documented Solariot register map and Sungrow-Modbus wire protocol behavior.
No third-party client implementation or embedded protocol secret is vendored.
