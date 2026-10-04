"""UI-only setup; device configuration remains in HA storage."""

import uuid

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_INTERVAL, DOMAIN
from .protocol import NegotiationRejected, ProtocolError, SungrowClient


def schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required("host", default=defaults.get("host", "")): str,
            vol.Required("port", default=defaults.get("port", 502)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required("unit", default=defaults.get("unit", 1)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=247)
            ),
            vol.Required(
                "scan_interval", default=defaults.get("scan_interval", DEFAULT_INTERVAL)
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
            vol.Optional(
                "protocol_key", default=defaults.get("protocol_key", "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


async def validate(data):
    host = data["host"].strip().lower()
    if not host or any(char in host for char in "/@?# \\"):
        return {"host": "invalid_host"}
    key = data.get("protocol_key", "").strip()
    try:
        key_bytes = bytes.fromhex(key) if key else None
        if key_bytes is not None and len(key_bytes) != 16:
            return {"protocol_key": "invalid_key"}
    except ValueError:
        return {"protocol_key": "invalid_key"}
    try:
        await SungrowClient(
            host, data.get("port", 502), data.get("unit", 1), key_bytes
        ).read()
    except NegotiationRejected:
        return {"base": "negotiation_rejected"}
    except ProtocolError:
        return {"base": "cannot_connect"}
    data["host"] = host
    data["protocol_key"] = key
    return {}


class SungrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Validate reachability before creating the integration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SungrowOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {
                    "host": user_input["host"].strip().lower(),
                    "unit": user_input.get("unit", 1),
                }
            )
            errors = await validate(user_input)
            if not errors:
                # Random installation identifier: never put host, MAC or serial in IDs.
                await self.async_set_unique_id(uuid.uuid4().hex)
                return self.async_create_entry(title="Sungrow Local", data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=schema(user_input), errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {
                    "host": user_input["host"].strip().lower(),
                    "unit": user_input.get("unit", 1),
                }
            )
            errors = await validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema(entry.data), errors=errors
        )


class SungrowOptionsFlow(config_entries.OptionsFlow):
    """Change polling cadence without changing sensor identities."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            "scan_interval",
            self.config_entry.data.get("scan_interval", DEFAULT_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("scan_interval", default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=3600)
                    ),
                }
            ),
        )
