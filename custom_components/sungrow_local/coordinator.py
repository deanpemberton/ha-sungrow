"""Coordinated polling avoids one connection per sensor."""

import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_INTERVAL, DOMAIN
from .protocol import ProtocolError, SungrowClient

_LOGGER = logging.getLogger(__name__)


class SungrowCoordinator(DataUpdateCoordinator):
    """Update all sensors from one bounded read."""

    def __init__(self, hass, entry):
        config = entry.data | entry.options
        key = config.get("protocol_key", "")
        self.client = SungrowClient(
            config["host"],
            config.get("port", 502),
            config.get("unit", 1),
            bytes.fromhex(key) if key else None,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=config.get("scan_interval", DEFAULT_INTERVAL)
            ),
            always_update=False,
        )

    async def _async_update_data(self):
        try:
            return await self.client.read()
        except ProtocolError:
            raise UpdateFailed("Unable to read inverter") from None
