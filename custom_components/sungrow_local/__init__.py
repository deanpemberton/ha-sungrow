"""Read-only Sungrow local telemetry."""

from homeassistant.const import Platform

from .coordinator import SungrowCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    """Initialize a single polling coordinator."""
    coordinator = SungrowCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    """Unload sensors and cancel coordinator polling subscriptions."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
