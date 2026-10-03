"""Native sensor metadata for MPPT comparison and power dashboards."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

DESCRIPTIONS = tuple(
    SensorEntityDescription(
        key=key,
        name=name,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
    )
    for key, name, unit, device_class, precision in (
        ("mppt1_voltage", "MPPT 1 voltage", "V", SensorDeviceClass.VOLTAGE, 1),
        ("mppt1_current", "MPPT 1 current", "A", SensorDeviceClass.CURRENT, 1),
        ("mppt1_power", "MPPT 1 power", "W", SensorDeviceClass.POWER, 0),
        ("mppt2_voltage", "MPPT 2 voltage", "V", SensorDeviceClass.VOLTAGE, 1),
        ("mppt2_current", "MPPT 2 current", "A", SensorDeviceClass.CURRENT, 1),
        ("mppt2_power", "MPPT 2 power", "W", SensorDeviceClass.POWER, 0),
        ("dc_power", "Total DC power", "W", SensorDeviceClass.POWER, 0),
        ("ac_power", "AC output power", "W", SensorDeviceClass.POWER, 0),
        ("temperature", "Inverter temperature", "°C", SensorDeviceClass.TEMPERATURE, 1),
        ("frequency", "Grid frequency", "Hz", SensorDeviceClass.FREQUENCY, 1),
    )
)
PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        SungrowSensor(entry.runtime_data, entry, description)
        for description in DESCRIPTIONS
    )


class SungrowSensor(CoordinatorEntity, SensorEntity):
    """All values share a coordinator and availability state."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name="Sungrow inverter",
            manufacturer="Sungrow",
            model="SG5K-D",
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self.entity_description.key)
