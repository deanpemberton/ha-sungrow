"""Vendor-neutral read-only inverter driver contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DriverError(Exception):
    """Sanitized inverter communication failure."""


@dataclass(frozen=True, slots=True)
class DriverMetadata:
    """Device metadata exposed to Home Assistant."""

    manufacturer: str
    model: str
    name: str


@dataclass(frozen=True, slots=True)
class SensorSpec:
    """Vendor-neutral sensor description."""

    key: str
    name: str
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    precision: int | None = None


class InverterDriver(Protocol):
    """Small contract shared by all supported inverter drivers."""

    @property
    def metadata(self) -> DriverMetadata:
        """Return device metadata after the first successful read."""

    @property
    def sensor_specs(self) -> tuple[SensorSpec, ...]:
        """Return sensor definitions for this inverter."""

    async def read(self) -> dict[str, Any]:
        """Return one normalized telemetry snapshot."""

    def mqtt_payload(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Return MQTT payload derived from the already-read snapshot."""


def create_driver(config: dict[str, Any]) -> InverterDriver:
    """Create the configured vendor driver.

    Existing entries pre-date the vendor field and are treated as Sungrow.
    """
    vendor = config.get("vendor", "sungrow")
    if vendor == "goodwe":
        from .goodwe_driver import GoodWeDriver

        return GoodWeDriver(
            host=config["host"],
            transport=config.get("transport", "auto"),
            port=config.get("port"),
            timeout=config.get("timeout", 3),
        )

    from .sungrow_driver import SungrowDriver

    key = config.get("protocol_key", "")
    return SungrowDriver(
        host=config["host"],
        port=config.get("port", 502),
        unit=config.get("unit", 1),
        protocol_key=bytes.fromhex(key) if key else None,
    )
