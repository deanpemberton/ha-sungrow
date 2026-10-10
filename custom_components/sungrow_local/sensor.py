"""Home Assistant sensors for vendor-neutral inverter telemetry."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

DEVICE_CLASSES = {
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "frequency": SensorDeviceClass.FREQUENCY,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "duration": SensorDeviceClass.DURATION,
    "timestamp": SensorDeviceClass.TIMESTAMP,
}
STATE_CLASSES = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total": SensorStateClass.TOTAL,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        InverterSensor(coordinator, entry, spec)
        for spec in coordinator.driver.sensor_specs
    )


class InverterSensor(CoordinatorEntity, SensorEntity):
    """One value from the coordinator's shared inverter snapshot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, spec):
        super().__init__(coordinator)
        self._key = spec.key
        self.entity_description = SensorEntityDescription(
            key=spec.key,
            name=spec.name,
            native_unit_of_measurement=spec.unit,
            device_class=DEVICE_CLASSES.get(spec.device_class),
            state_class=STATE_CLASSES.get(spec.state_class),
            suggested_display_precision=spec.precision,
        )
        metadata = coordinator.driver.metadata
        self._attr_unique_id = f"{entry.unique_id}_{spec.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=metadata.name,
            manufacturer=metadata.manufacturer,
            model=metadata.model,
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key)
