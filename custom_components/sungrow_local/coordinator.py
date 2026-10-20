"""Coordinated polling and MQTT publication from one inverter snapshot."""

import asyncio
import json
import logging
from time import monotonic
from datetime import UTC, datetime, timedelta

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_INTERVAL, DEFAULT_MQTT_TOPIC, DOMAIN
from .driver import DriverError, create_driver

_LOGGER = logging.getLogger(__name__)


class InverterCoordinator(DataUpdateCoordinator):
    """Update all consumers from one rate-conscious inverter read."""

    def __init__(self, hass, entry):
        config = entry.data | entry.options
        self.driver = create_driver(config)
        self._mqtt_topic = config.get("mqtt_topic", DEFAULT_MQTT_TOPIC).strip()
        if "/" in self._mqtt_topic:
            prefix = self._mqtt_topic.rsplit("/", 1)[0]
        else:
            prefix = self._mqtt_topic
        self._mqtt_status_topic = f"{prefix}/status"
        self._mqtt_last_warning = 0.0
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

    async def _async_publish_mqtt(self, snapshot, available: bool) -> None:
        if (
            not self._mqtt_topic
            or not self.hass.services.has_service("mqtt", "publish")
        ):
            return
        try:
            await asyncio.wait_for(self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": self._mqtt_status_topic,
                    "payload": "online" if available else "offline",
                    "retain": True,
                    "qos": 0,
                },
                blocking=True,
            ), timeout=5)
            if available:
                payload = self.driver.mqtt_payload(snapshot)
                payload["_source"] = DOMAIN
                payload["_last_update"] = datetime.now(UTC).isoformat()
                await asyncio.wait_for(self.hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": self._mqtt_topic,
                        "payload": json.dumps(
                            payload, separators=(",", ":"), default=str
                        ),
                        "retain": True,
                        "qos": 0,
                    },
                    blocking=True,
                )
        except (Exception, asyncio.TimeoutError) as exc:
            # MQTT is optional: never discard a successful inverter read.
            # Throttle repeated failures while preserving the error type.
            now = monotonic()
            if now - self._mqtt_last_warning >= 300 or self._mqtt_last_warning == 0:
                _LOGGER.warning("Inverter MQTT publish failed (%s); retrying on next poll", type(exc).__name__)
                self._mqtt_last_warning = now

    async def _async_update_data(self):
        try:
            snapshot = await self.driver.read()
        except DriverError:
            await self._async_publish_mqtt({}, False)
            raise UpdateFailed("Unable to read inverter") from None
        await self._async_publish_mqtt(snapshot, True)
        return snapshot
