"""Read-only local solar inverter integration."""

from homeassistant.const import Platform

from .coordinator import InverterCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_migrate_entry(hass, entry):
    """Migrate pre-vendor entries without changing entity identities."""
    if entry.version == 1:
        data = {**entry.data, "vendor": "sungrow"}
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass, entry):
    """Initialize one local inverter polling coordinator."""
    coordinator = InverterCoordinator(hass, entry)
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
