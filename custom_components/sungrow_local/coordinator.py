"""Coordinated polling and MQTT publication from one inverter snapshot."""

import importlib
import json
import logging
from datetime import UTC, datetime, timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import protocol
from .const import DEFAULT_INTERVAL, DEFAULT_MQTT_TOPIC, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SungrowCoordinator(DataUpdateCoordinator):
    """Update all consumers from one rate-conscious inverter read."""

    def __init__(self, hass, entry):
        config = entry.data | entry.options
        key = config.get("protocol_key", "")
        current_protocol = importlib.reload(protocol)
        self.protocol = current_protocol
        self.client = current_protocol.SungrowClient(
            config["host"],
            config.get("port", 502),
            config.get("unit", 1),
            bytes.fromhex(key) if key else None,
        )
        self._mqtt_topic = config.get(
            "mqtt_topic", DEFAULT_MQTT_TOPIC
        ).strip()
        if "/" in self._mqtt_topic:
            prefix = self._mqtt_topic.rsplit("/", 1)[0]
        else:
            prefix = self._mqtt_topic
        self._mqtt_status_topic = f"{prefix}/status"
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
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": self._mqtt_status_topic,
                    "payload": "online" if available else "offline",
                    "retain": True,
                    "qos": 0,
                },
                blocking=False,
            )
            if available:
                payload = self.protocol.mqtt_payload(snapshot)
                payload["_source"] = DOMAIN
                payload["_last_update"] = datetime.now(UTC).isoformat()
                await self.hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": self._mqtt_topic,
                        "payload": json.dumps(
                            payload, separators=(",", ":")
                        ),
                        "retain": True,
                        "qos": 0,
                    },
                    blocking=False,
                )
        except Exception:
            _LOGGER.warning("Unable to publish Sungrow telemetry to MQTT")

    async def _async_update_data(self):
        try:
            snapshot = await self.client.read()
        except self.protocol.ProtocolError:
            await self._async_publish_mqtt({}, False)
            raise UpdateFailed("Unable to read inverter") from None
        await self._async_publish_mqtt(snapshot, True)
        return snapshot
