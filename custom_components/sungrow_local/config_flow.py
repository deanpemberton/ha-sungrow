"""UI setup for supported local solar inverter vendors."""

import uuid

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_INTERVAL, DEFAULT_MQTT_TOPIC, DOMAIN, MIN_INTERVAL
from .driver import DriverError, create_driver

VENDORS = {"sungrow": "Sungrow", "goodwe": "GoodWe"}


def common_fields(defaults=None):
    defaults = defaults or {}
    return {
        vol.Required(
            "scan_interval", default=defaults.get("scan_interval", DEFAULT_INTERVAL)
        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_INTERVAL, max=3600)),
        vol.Optional(
            "mqtt_topic", default=defaults.get("mqtt_topic", DEFAULT_MQTT_TOPIC)
        ): str,
    }


def sungrow_schema(defaults=None):
    defaults = defaults or {}
    fields = {
        vol.Required("host", default=defaults.get("host", "")): str,
        vol.Required("port", default=defaults.get("port", 502)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required("unit", default=defaults.get("unit", 1)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=247)
        ),
        vol.Optional(
            "protocol_key", default=defaults.get("protocol_key", "")
        ): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
    fields.update(common_fields(defaults))
    return vol.Schema(fields)


def goodwe_schema(defaults=None):
    defaults = defaults or {}
    if "mqtt_topic" not in defaults:
        defaults = {**defaults, "mqtt_topic": "inverter/goodwe/stats"}
    fields = {
        vol.Required("host", default=defaults.get("host", "")): str,
        vol.Required(
            "transport", default=defaults.get("transport", "auto")
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": "auto", "label": "Auto (UDP 8899, then TCP 502)"},
                    {"value": "udp", "label": "UDP / SolarGo (8899)"},
                    {"value": "tcp", "label": "Modbus TCP (502)"},
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional("port", default=defaults.get("port", 0)): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=65535)
        ),
    }
    fields.update(common_fields(defaults))
    return vol.Schema(fields)


def _clean_host(data):
    host = data["host"].strip().lower()
    if not host or any(char in host for char in "/@?# \\\\"):
        return None
    data["host"] = host
    data["mqtt_topic"] = data.get("mqtt_topic", DEFAULT_MQTT_TOPIC).strip()
    return host


async def validate(data):
    """Validate one read-only snapshot through the selected driver."""
    if not _clean_host(data):
        return {"host": "invalid_host"}

    key = data.get("protocol_key", "").strip()
    if data.get("vendor", "sungrow") == "sungrow":
        try:
            key_bytes = bytes.fromhex(key) if key else None
            if key_bytes is not None and len(key_bytes) != 16:
                return {"protocol_key": "invalid_key"}
        except ValueError:
            return {"protocol_key": "invalid_key"}
        data["protocol_key"] = key

    try:
        await create_driver(data).read()
    except DriverError:
        return {"base": "cannot_connect"}
    return {}


class SungrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure any supported local inverter."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return InverterOptionsFlow()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            vendor = user_input["vendor"]
            if vendor == "goodwe":
                return await self.async_step_goodwe()
            return await self.async_step_sungrow()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "vendor", default="sungrow"
                    ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"value": key, "label": value}
                                    for key, value in VENDORS.items()
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        )
                }
            ),
        )

    async def _finish_vendor(self, vendor, user_input, schema):
        errors = {}
        if user_input is not None:
            data = {"vendor": vendor, **user_input}
            match = {"host": user_input["host"].strip().lower(), "vendor": vendor}
            self._async_abort_entries_match(match)
            errors = await validate(data)
            if not errors:
                await self.async_set_unique_id(uuid.uuid4().hex)
                title = "GoodWe Local" if vendor == "goodwe" else "Sungrow Local"
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(
            step_id=vendor, data_schema=schema(user_input), errors=errors
        )

    async def async_step_sungrow(self, user_input=None):
        return await self._finish_vendor("sungrow", user_input, sungrow_schema)

    async def async_step_goodwe(self, user_input=None):
        return await self._finish_vendor("goodwe", user_input, goodwe_schema)

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        vendor = entry.data.get("vendor", "sungrow")
        schema = goodwe_schema if vendor == "goodwe" else sungrow_schema
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input, "vendor": vendor}
            errors = await validate(data)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=data
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema(entry.data | entry.options),
            errors=errors,
        )


class InverterOptionsFlow(config_entries.OptionsFlow):
    """Change polling cadence and MQTT publication."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            "scan_interval",
            self.config_entry.data.get("scan_interval", DEFAULT_INTERVAL),
        )
        mqtt_topic = self.config_entry.options.get(
            "mqtt_topic",
            self.config_entry.data.get("mqtt_topic", DEFAULT_MQTT_TOPIC),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("scan_interval", default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_INTERVAL, max=3600),
                    ),
                    vol.Optional("mqtt_topic", default=mqtt_topic): str,
                }
            ),
        )
