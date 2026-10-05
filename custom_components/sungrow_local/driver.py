"""Vendor-neutral read-only inverter driver boundary."""

from dataclasses import dataclass
from typing import Protocol

from .protocol import SungrowClient


@dataclass(frozen=True, slots=True)
class InverterMetadata:
    """Stable device metadata supplied by an inverter driver."""

    manufacturer: str
    model: str


class InverterDriver(Protocol):
    """Minimal interface consumed by the Home Assistant coordinator."""

    metadata: InverterMetadata

    async def read(self) -> dict[str, float | None]:
        """Return one coherent normalized telemetry snapshot."""


class SungrowSG5KDDriver:
    """Read-only SG5K-D driver using the local Sungrow transport."""

    metadata = InverterMetadata(manufacturer="Sungrow", model="SG5K-D")

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit: int = 1,
        protocol_key: bytes | None = None,
        timeout: int = 10,
    ) -> None:
        self._client = SungrowClient(host, port, unit, protocol_key, timeout)

    async def read(self) -> dict[str, float | None]:
        """Return normalized SG5K-D telemetry."""
        return await self._client.read()


def create_driver(config: dict) -> InverterDriver:
    """Build the configured inverter driver.

    The factory is intentionally small so future vendors can be added without
    changing the coordinator or sensor entity implementation.
    """
    key = config.get("protocol_key", "")
    return SungrowSG5KDDriver(
        config["host"],
        config.get("port", 502),
        config.get("unit", 1),
        bytes.fromhex(key) if key else None,
    )
