# ruff: noqa: E501,I001
"""Sungrow SG5K-D driver adapter."""

from __future__ import annotations

from typing import Any

from .driver import DriverError, DriverMetadata, SensorSpec
from . import protocol


# fmt: off
SPECS = (
    SensorSpec("nominal_active_power", "Nominal active power", "W", "power", precision=0),
    SensorSpec("daily_energy", "Daily energy", "kWh", "energy", "total_increasing", 1),
    SensorSpec("legacy_total_energy", "Legacy total energy", "kWh", "energy", "total_increasing", 0),
    SensorSpec("total_energy", "Total energy", "kWh", "energy", "total_increasing", 1),
    SensorSpec("total_running_time", "Total running time", "h", "duration", "total_increasing", 0),
    SensorSpec("daily_running_time", "Daily running time", "min", "duration", "total_increasing", 0),
    SensorSpec("temperature", "Inverter temperature", "°C", "temperature", precision=1),
    SensorSpec("apparent_power", "Apparent power", "VA", precision=0),
    SensorSpec("mppt1_voltage", "MPPT 1 voltage", "V", "voltage", precision=1),
    SensorSpec("mppt1_current", "MPPT 1 current", "A", "current", precision=1),
    SensorSpec("mppt1_power", "MPPT 1 power", "W", "power", precision=0),
    SensorSpec("mppt2_voltage", "MPPT 2 voltage", "V", "voltage", precision=1),
    SensorSpec("mppt2_current", "MPPT 2 current", "A", "current", precision=1),
    SensorSpec("mppt2_power", "MPPT 2 power", "W", "power", precision=0),
    SensorSpec("dc_power", "Total DC power", "W", "power", precision=0),
    SensorSpec("phase_a_voltage", "Phase A voltage", "V", "voltage", precision=1),
    SensorSpec("phase_b_voltage", "Phase B voltage", "V", "voltage", precision=1),
    SensorSpec("phase_c_voltage", "Phase C voltage", "V", "voltage", precision=1),
    SensorSpec("phase_a_current", "Phase A current", "A", "current", precision=1),
    SensorSpec("phase_b_current", "Phase B current", "A", "current", precision=1),
    SensorSpec("phase_c_current", "Phase C current", "A", "current", precision=1),
    SensorSpec("ac_power", "AC output power", "W", "power", precision=0),
    SensorSpec("reactive_power", "Reactive power", "var", precision=0),
    SensorSpec("power_factor", "Power factor", precision=3),
    SensorSpec("frequency", "Grid frequency", "Hz", "frequency", precision=1),
    SensorSpec("device_status", "Device status", state_class=None, precision=0),
    SensorSpec("fault_code", "Fault code", state_class=None, precision=0),
    SensorSpec("nominal_reactive_power", "Nominal reactive power", "var", precision=0),
    SensorSpec("grid_power", "Grid power", "W", "power", precision=0),
    SensorSpec("meter_phase_a_power", "Meter phase A power", "W", "power", precision=0),
    SensorSpec("meter_phase_b_power", "Meter phase B power", "W", "power", precision=0),
    SensorSpec("meter_phase_c_power", "Meter phase C power", "W", "power", precision=0),
    SensorSpec("house_power", "House power", "W", "power", precision=0),
    SensorSpec("daily_import_energy", "Daily imported energy", "kWh", "energy", "total_increasing", 1),
    SensorSpec("daily_consumption", "Daily energy consumption", "kWh", "energy", "total_increasing", 1),
    SensorSpec("total_consumption", "Total energy consumption", "kWh", "energy", "total_increasing", 1),
    SensorSpec("negative_voltage_to_ground", "Negative voltage to ground", "V", "voltage", precision=1),
    SensorSpec("frequency_high_resolution", "Grid frequency high resolution", "Hz", "frequency", precision=2),
)
# fmt: on


class SungrowDriver:
    """Rate-conscious SG5K-D driver."""

    def __init__(self, host: str, port: int = 502, unit: int = 1, protocol_key=None):
        self._client = protocol.SungrowClient(host, port, unit, protocol_key)

    @property
    def metadata(self) -> DriverMetadata:
        return DriverMetadata("Sungrow", "SG5K-D", "Sungrow inverter")

    @property
    def sensor_specs(self) -> tuple[SensorSpec, ...]:
        return SPECS

    async def read(self) -> dict[str, Any]:
        try:
            return await self._client.read()
        except protocol.ProtocolError:
            raise DriverError("Unable to read inverter") from None

    def mqtt_payload(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return protocol.mqtt_payload(snapshot)
