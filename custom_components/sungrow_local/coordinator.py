"""Coordinated polling avoids one connection per sensor."""

import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_INTERVAL, DOMAIN
from .driver import InverterDriver, create_driver
from .protocol import ProtocolError

_LOGGER = logging.getLogger(__name__)


class SungrowCoordinator(DataUpdateCoordinator):
    """Update all sensors from one bounded inverter read."""

    def __init__(self, hass, entry, driver: InverterDriver | None = None):
        config = entry.data | entry.options
        self.driver = driver or create_driver(config)
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
            return await self.driver.read()
        except ProtocolError:
            raise UpdateFailed("Unable to read inverter") from None
