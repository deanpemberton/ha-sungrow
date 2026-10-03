# Installation and setup

## Before you start

- Home Assistant 2026.2 or newer. Automated integration tests currently use
  Home Assistant 2026.2.3; later versions have not yet been validated on hardware.
- A Sungrow SG5K-D and a network-connected communication dongle that provides
  compatible plain Modbus TCP or legacy encrypted Sungrow TCP.
- Home Assistant must be able to reach the dongle on your local network.
- Access to the Home Assistant configuration directory, for example through
  an existing network share, SSH or a container/host configuration mount.

This version is experimental and has not been tested against live hardware.
It does not implement the legacy web transport used by some dongles. Keep your
existing working telemetry source until you have compared the new readings.
No MQTT broker, extra container, iSolarCloud login or YAML configuration is needed.

## 1. Download the integration

For the current draft implementation:

1. Open this repository in GitHub.
2. Open the branch selector and choose **feature/1-local-telemetry**.
3. Choose **Code → Download ZIP** and extract the archive on your computer.
4. Inside the extracted archive, locate `custom_components/sungrow_local`.

After the PR has been reviewed and merged, use `develop` for development builds.
Use a published release for routine installation once one is available. Do not
assume the repository's default branch contains this unmerged implementation.

## 2. Copy the files into Home Assistant

1. Find Home Assistant's configuration directory: the directory that contains
   `configuration.yaml`. On Home Assistant OS it is normally `/config`; for
   Container/Core installations use the configured persistent configuration path.
2. Create a `custom_components` directory there if it does not exist.
3. Copy the entire **sungrow_local** folder into that directory.

The final file locations should include:

```text
/config/custom_components/sungrow_local/__init__.py
/config/custom_components/sungrow_local/manifest.json
/config/custom_components/sungrow_local/config_flow.py
/config/custom_components/sungrow_local/coordinator.py
/config/custom_components/sungrow_local/protocol.py
/config/custom_components/sungrow_local/sensor.py
/config/custom_components/sungrow_local/strings.json
/config/custom_components/sungrow_local/translations/en.json
```

Do not copy the outer ZIP directory into `custom_components`, and do not nest
another `sungrow_local` folder inside it. Copy only the integration folder;
`tests`, development dependencies and CI files do not belong in HA's config.

4. Restart **Home Assistant itself**, not just a terminal or file-editor app.
   Use Settings → System → the power menu → Restart Home Assistant.
5. Wait for Home Assistant to finish starting.

## 3. Add the integration

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Sungrow Local** and select it.
3. Enter these settings:

| Field | What to enter |
|---|---|
| Inverter hostname or IP address | The dongle's local address; enter it here only. Do not include `http://` or a path. |
| TCP port | Normally `502`; use the port your device actually provides. |
| Inverter unit ID | Normally `1`; this identifies the inverter, not the WiFi module's own address. |
| Polling interval | Start with `30` seconds. |
| Protocol key | Leave empty for plain Modbus TCP. For a compatible encrypted dongle, enter its 16-byte protocol key as 32 hexadecimal characters. |

The protocol key is **not your iSolarCloud password**. This repository does not
contain a key and cannot supply one. If the old working collector used encryption,
consult its local configuration/documentation privately. Do not paste any key
into a GitHub issue, commit or screenshot. No automatic transport detection is
provided: the integration negotiates encrypted transport only when a key is set.

4. Submit the form. Setup performs a read to validate communication.
5. When successful, open the integration's **Sungrow inverter** device to see its
   ten sensors: six MPPT sensors, DC power, AC output power, temperature and frequency.

## 4. Check the first readings

Test during daylight while the inverter is generating:

- Compare both MPPT voltages and currents with the inverter's own display or
  available diagnostics. Confirm which tracker corresponds to each physical string
  before renaming entities or assigning east/west labels.
- Each calculated MPPT power should equal its voltage multiplied by its current.
- Compare total DC and AC output power. They need not match exactly: conversion
  losses and inverter clipping affect AC output.
- Cloud values can be delayed; compare their measurement times before interpreting
  a difference as a fault.
- An inactive string may correctly report zero. Missing register values are unknown;
  failed communication makes the sensors unavailable instead of preserving stale power.

Add the desired sensors through a dashboard's Edit → Add card flow. These are
instantaneous measurements; they are not energy counters for the Energy dashboard.
Measured daily/lifetime energy counters are planned separately.

## HACS status

`hacs.json` is included, but this draft has no release and is not listed in the
HACS default repository catalogue. **Use the manual installation above for now.**
HACS installation will be documented and verified when a release is available.
Adding a custom repository alone does not ensure it contains the unmerged feature
branch or that it can install this build.

## Change settings

- **Polling interval:** Settings → Devices & services → Sungrow Local → Configure
  (integration options). Choose 10–3600 seconds; 30 seconds is the starting default.
- **Device address, port, unit or protocol key:** use the integration entry's menu
  → Reconfigure. Reconfiguration validates the connection and preserves sensor IDs.
- Reserve the dongle's address in your router if desired so its address remains
  stable. Make that change locally, without committing network details.

## Update a manual installation

1. Download the desired reviewed branch/release and extract it.
2. Make a private copy of the current `custom_components/sungrow_local` folder
   outside `custom_components` so you can roll back.
3. Replace that folder with the downloaded version. Avoid leaving duplicate
   copies inside `custom_components`.
4. Restart Home Assistant and check the integration and readings.

The integration's settings remain in HA local storage. Do not edit or upload
`.storage` files. To roll back, restore the saved integration folder and restart.

## Troubleshooting

| Symptom | Checks |
|---|---|
| Sungrow Local does not appear | Confirm the folder placement and that `manifest.json` exists. Restart HA fully, refresh the browser/app, then check Settings → System → Logs. |
| Setup says Unable to read inverter | Confirm the local address, port and unit ID; verify HA can reach the device across any network segments; check whether the dongle requires encrypted or unsupported web transport. |
| Port is open but setup fails | An open port does not prove Modbus compatibility. Check transport mode, key, firmware and unit ID. |
| Sensors become unavailable | Check inverter/dongle power and WiFi, address changes, network rules and competing clients. The coordinator retries on subsequent polls. |
| One MPPT is unknown | The register reported an unavailable value. Check the tracker on the device; do not substitute zero. |
| Values look implausible | Compare raw displayed device measurements privately. Stop using these entities for decisions until register mapping is validated. |

Errors deliberately omit connection details. When reporting a bug, include the
integration version, HA version, inverter/dongle model, transport mode and the
sanitized error message. Remove addresses, hostnames, MACs, serials, keys, account
information and personal details from any material you share.

## Remove the integration

1. Settings → Devices & services → Sungrow Local → entry menu → Delete.
2. For a manual installation, remove `custom_components/sungrow_local` and restart HA.
3. Remove dashboard references to deleted entities if needed.

Removing this read-only integration does not change inverter settings.
