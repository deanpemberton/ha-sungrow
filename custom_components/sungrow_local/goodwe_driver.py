# ruff: noqa: E501
"""GoodWe MS G3 read-only local driver.

Uses the mature upstream goodwe library used by Home Assistant's native
integration, then normalizes the important values into the shared schema while
retaining every additional runtime sensor exposed by the library.
"""

from __future__ import annotations

import logging
from typing import Any

import goodwe
from goodwe.exceptions import InverterError

from .driver import DriverError, DriverMetadata, SensorSpec

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 8899
MODBUS_TCP_PORT = 502

# Upstream GoodWe sensor id -> stable cross-vendor key.
COMMON_KEYS = {
    "vpv1": "mppt1_voltage",
    "ipv1": "mppt1_current",
    "ppv1": "mppt1_power",
    "vpv2": "mppt2_voltage",
    "ipv2": "mppt2_current",
    "ppv2": "mppt2_power",
    "vpv3": "mppt3_voltage",
    "ipv3": "mppt3_current",
    "ppv3": "mppt3_power",
    "total_input_power": "dc_power",
    "total_inverter_power": "ac_power",
    "apparent_power": "apparent_power",
    "reactive_power": "reactive_power",
    "power_factor": "power_factor",
    "warning_code": "warning_code",
    "vgrid1": "phase_a_voltage",
    "igrid1": "phase_a_current",
    "fgrid1": "frequency",
    "temperature": "temperature",
    "e_day": "daily_energy",
    "e_total": "total_energy",
    "h_total": "total_running_time",
    "work_mode": "device_status",
    "error_codes": "fault_code",
    "meter_active_power": "grid_power",
    "meter_e_total_exp": "total_export_energy",
    "meter_e_total_imp": "total_import_energy",
    "house_consumption": "house_power",
}

# fmt: off
COMMON_SPECS = {
    "mppt1_voltage": SensorSpec("mppt1_voltage", "MPPT 1 voltage", "V", "voltage", precision=1),
    "mppt1_current": SensorSpec("mppt1_current", "MPPT 1 current", "A", "current", precision=1),
    "mppt1_power": SensorSpec("mppt1_power", "MPPT 1 power", "W", "power", precision=0),
    "mppt2_voltage": SensorSpec("mppt2_voltage", "MPPT 2 voltage", "V", "voltage", precision=1),
    "mppt2_current": SensorSpec("mppt2_current", "MPPT 2 current", "A", "current", precision=1),
    "mppt2_power": SensorSpec("mppt2_power", "MPPT 2 power", "W", "power", precision=0),
    "mppt3_voltage": SensorSpec("mppt3_voltage", "MPPT 3 voltage", "V", "voltage", precision=1),
    "mppt3_current": SensorSpec("mppt3_current", "MPPT 3 current", "A", "current", precision=1),
    "mppt3_power": SensorSpec("mppt3_power", "MPPT 3 power", "W", "power", precision=0),
    "dc_power": SensorSpec("dc_power", "Total DC power", "W", "power", precision=0),
    "ac_power": SensorSpec("ac_power", "AC output power", "W", "power", precision=0),
    "apparent_power": SensorSpec("apparent_power", "Apparent power", "VA", precision=0),
    "reactive_power": SensorSpec("reactive_power", "Reactive power", "var", precision=0),
    "power_factor": SensorSpec("power_factor", "Power factor", precision=3),
    "warning_code": SensorSpec("warning_code", "Warning code", state_class=None, precision=0),
    "phase_a_voltage": SensorSpec("phase_a_voltage", "Grid voltage", "V", "voltage", precision=1),
    "phase_a_current": SensorSpec("phase_a_current", "Grid current", "A", "current", precision=1),
    "frequency": SensorSpec("frequency", "Grid frequency", "Hz", "frequency", precision=2),
    "temperature": SensorSpec("temperature", "Inverter temperature", "°C", "temperature", precision=1),
    "daily_energy": SensorSpec("daily_energy", "Daily energy", "kWh", "energy", "total_increasing", 1),
    "total_energy": SensorSpec("total_energy", "Total energy", "kWh", "energy", "total_increasing", 1),
    "total_running_time": SensorSpec("total_running_time", "Total running time", "h", "duration", "total_increasing", 0),
    "device_status": SensorSpec("device_status", "Device status", state_class=None, precision=0),
    "fault_code": SensorSpec("fault_code", "Fault code", state_class=None, precision=0),
    "grid_power": SensorSpec("grid_power", "Meter active power", "W", "power", precision=0),
    "total_export_energy": SensorSpec("total_export_energy", "Meter total export energy", "kWh", "energy", "total_increasing", 2),
    "total_import_energy": SensorSpec("total_import_energy", "Meter total import energy", "kWh", "energy", "total_increasing", 2),
    "house_power": SensorSpec("house_power", "House consumption", "W", "power", precision=0),
}
# fmt: on


def _sensor_spec(sensor) -> SensorSpec:
    """Translate upstream sensor metadata without hard-coding future additions."""
    key = f"goodwe_{sensor.id_}"
    unit = sensor.unit or None
    device_class = None
    state_class = "measurement"
    precision = None

    if sensor.id_ == "timestamp":
        device_class = "timestamp"
        state_class = None
    elif unit == "V":
        device_class, precision = "voltage", 1
    elif unit == "A":
        device_class, precision = "current", 1
    elif unit == "W":
        device_class, precision = "power", 0
    elif unit == "Hz":
        device_class, precision = "frequency", 2
    elif unit in ("C", "°C"):
        device_class, unit, precision = "temperature", "°C", 1
    elif unit == "kWh":
        device_class, state_class, precision = "energy", "total_increasing", 2
    elif unit == "h":
        device_class, precision = "duration", 0
        if sensor.id_ == "h_total":
            state_class = "total_increasing"
    elif unit == "%":
        precision = 0

    # Labels and bitmap descriptions are strings rather than measurements.
    if sensor.id_.endswith("_label"):
        state_class = None

    return SensorSpec(
        key=key,
        name=sensor.name,
        unit=unit,
        device_class=device_class,
        state_class=state_class,
        precision=precision,
    )


class GoodWeDriver:
    """Read-only GoodWe MS/MS G3 driver with conservative transport discovery."""

    def __init__(
        self,
        host: str,
        transport: str = "auto",
        port: int | None = None,
        timeout: int = 3,
    ):
        self._host = host
        self._transport = transport
        self._configured_port = port or 0
        self._timeout = timeout
        self._inverter = None
        self._selected_port: int | None = None
        self._metadata = DriverMetadata("GoodWe", "MS G3", "GoodWe inverter")
        self._sensor_specs: tuple[SensorSpec, ...] = ()

    @property
    def metadata(self) -> DriverMetadata:
        return self._metadata

    @property
    def sensor_specs(self) -> tuple[SensorSpec, ...]:
        return self._sensor_specs

    def _candidate_ports(self) -> list[int]:
        if self._selected_port is not None:
            return [self._selected_port]
        if self._transport == "udp":
            return [self._configured_port or UDP_PORT]
        if self._transport == "tcp":
            return [self._configured_port or MODBUS_TCP_PORT]

        ports: list[int] = []
        if self._configured_port:
            ports.append(self._configured_port)
        for port in (UDP_PORT, MODBUS_TCP_PORT):
            if port not in ports:
                ports.append(port)
        return ports

    async def _connect(self):
        if self._inverter is not None:
            return self._inverter

        for port in self._candidate_ports():
            try:
                inverter = await goodwe.connect(
                    self._host,
                    port=port,
                    timeout=self._timeout,
                    retries=1,
                )
                self._inverter = inverter
                self._selected_port = port
                model = inverter.model_name or "MS G3"
                self._metadata = DriverMetadata(
                    "GoodWe", model, f"GoodWe {model} inverter"
                )
                self._build_sensor_specs(inverter)
                _LOGGER.debug("GoodWe local transport selected port=%d", port)
                return inverter
            except InverterError:
                continue

        raise DriverError("Unable to read inverter")

    def _build_sensor_specs(self, inverter) -> None:
        specs: dict[str, SensorSpec] = {}
        for sensor in inverter.sensors():
            common_key = COMMON_KEYS.get(sensor.id_)
            if common_key:
                specs[common_key] = COMMON_SPECS[common_key]
                continue
            spec = _sensor_spec(sensor)
            specs[spec.key] = spec
        self._sensor_specs = tuple(specs.values())

    async def read(self) -> dict[str, Any]:
        try:
            inverter = await self._connect()
            raw = await inverter.read_runtime_data()
            self._build_sensor_specs(inverter)
        except InverterError:
            raise DriverError("Unable to read inverter") from None

        snapshot: dict[str, Any] = {}
        for key, value in raw.items():
            target = COMMON_KEYS.get(key, f"goodwe_{key}")
            snapshot[target] = value

        # Keep the library's calculated PV sum as a diagnostic while using the
        # inverter-reported total input power as the normalized DC value.
        if "ppv" in raw:
            snapshot["goodwe_calculated_pv_power"] = raw["ppv"]
        if snapshot.get("dc_power") is None:
            snapshot["dc_power"] = raw.get("ppv")

        return snapshot

    def mqtt_payload(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        payload = dict(snapshot)
        payload["_vendor"] = "goodwe"
        payload["_transport_port"] = self._selected_port
        return payload
