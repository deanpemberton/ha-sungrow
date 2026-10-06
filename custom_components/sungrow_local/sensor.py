"""Home Assistant sensors for the normalized SG5K-D telemetry snapshot."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def desc(
    key,
    name,
    unit=None,
    device_class=None,
    state_class=SensorStateClass.MEASUREMENT,
    precision=None,
):
    return SensorEntityDescription(
        key=key,
        name=name,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        suggested_display_precision=precision,
    )


DESCRIPTIONS = (
    desc("nominal_active_power", "Nominal active power", "W", SensorDeviceClass.POWER, precision=0),
    desc("daily_energy", "Daily energy", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, 1),
    desc("legacy_total_energy", "Legacy total energy", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, 0),
    desc("total_energy", "Total energy", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, 1),
    desc("total_running_time", "Total running time", "h", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING, 0),
    desc("daily_running_time", "Daily running time", "min", SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING, 0),
    desc("temperature", "Inverter temperature", "°C", SensorDeviceClass.TEMPERATURE, precision=1),
    desc("apparent_power", "Apparent power", "VA", precision=0),
    desc("mppt1_voltage", "MPPT 1 voltage", "V", SensorDeviceClass.VOLTAGE, precision=1),
    desc("mppt1_current", "MPPT 1 current", "A", SensorDeviceClass.CURRENT, precision=1),
    desc("mppt1_power", "MPPT 1 power", "W", SensorDeviceClass.POWER, precision=0),
    desc("mppt2_voltage", "MPPT 2 voltage", "V", SensorDeviceClass.VOLTAGE, precision=1),
    desc("mppt2_current", "MPPT 2 current", "A", SensorDeviceClass.CURRENT, precision=1),
    desc("mppt2_power", "MPPT 2 power", "W", SensorDeviceClass.POWER, precision=0),
    desc("dc_power", "Total DC power", "W", SensorDeviceClass.POWER, precision=0),
    desc("phase_a_voltage", "Phase A voltage", "V", SensorDeviceClass.VOLTAGE, precision=1),
    desc("phase_b_voltage", "Phase B voltage", "V", SensorDeviceClass.VOLTAGE, precision=1),
    desc("phase_c_voltage", "Phase C voltage", "V", SensorDeviceClass.VOLTAGE, precision=1),
    desc("phase_a_current", "Phase A current", "A", SensorDeviceClass.CURRENT, precision=1),
    desc("phase_b_current", "Phase B current", "A", SensorDeviceClass.CURRENT, precision=1),
    desc("phase_c_current", "Phase C current", "A", SensorDeviceClass.CURRENT, precision=1),
    desc("ac_power", "AC output power", "W", SensorDeviceClass.POWER, precision=0),
    desc("reactive_power", "Reactive power", "var", precision=0),
    desc("power_factor", "Power factor", precision=3),
    desc("frequency", "Grid frequency", "Hz", SensorDeviceClass.FREQUENCY, precision=1),
    desc("device_status", "Device status", state_class=None, precision=0),
    desc("fault_code", "Fault code", state_class=None, precision=0),
    desc("nominal_reactive_power", "Nominal reactive power", "var", precision=0),
    desc("grid_power", "Grid power", "W", SensorDeviceClass.POWER, precision=0),
    desc("house_power", "House power", "W", SensorDeviceClass.POWER, precision=0),
    desc("daily_import_energy", "Daily imported energy", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, 1),
    desc("daily_consumption", "Daily energy consumption", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, 1),
    desc("total_consumption", "Total energy consumption", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, 1),
    desc("negative_voltage_to_ground", "Negative voltage to ground", "V", SensorDeviceClass.VOLTAGE, precision=1),
)

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        SungrowSensor(entry.runtime_data, entry, description)
        for description in DESCRIPTIONS
    )


class SungrowSensor(CoordinatorEntity, SensorEntity):
    """All values share one coordinator and availability state."""

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
