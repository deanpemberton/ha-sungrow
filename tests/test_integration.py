"""Home Assistant behavior for the vendor-neutral local inverter integration."""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sungrow_local.const import DOMAIN
from custom_components.sungrow_local.driver import (
    DriverError,
    DriverMetadata,
    SensorSpec,
)


class FakeDriver:
    metadata = DriverMetadata("Test", "Synthetic", "Synthetic inverter")
    sensor_specs = (
        SensorSpec("ac_power", "AC output power", "W", "power", precision=0),
        SensorSpec("mppt1_power", "MPPT 1 power", "W", "power", precision=0),
    )

    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot or {"ac_power": 4200, "mppt1_power": 2200}
        self.error = error
        self.read = AsyncMock(side_effect=error, return_value=self.snapshot)

    def mqtt_payload(self, snapshot):
        return dict(snapshot)


async def _select_vendor(hass, vendor):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"vendor": vendor}
    )


async def test_sungrow_config_flow(hass):
    result = await _select_vendor(hass, "sungrow")
    assert result["step_id"] == "sungrow"
    driver = FakeDriver()
    with patch(
        "custom_components.sungrow_local.config_flow.create_driver",
        return_value=driver,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "inverter.invalid",
                "port": 502,
                "unit": 1,
                "scan_interval": 60,
                "mqtt_topic": "inverter/stats",
                "protocol_key": "",
            },
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["vendor"] == "sungrow"


async def test_goodwe_config_flow(hass):
    result = await _select_vendor(hass, "goodwe")
    assert result["step_id"] == "goodwe"
    driver = FakeDriver()
    with patch(
        "custom_components.sungrow_local.config_flow.create_driver",
        return_value=driver,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "goodwe.invalid",
                "transport": "auto",
                "port": 0,
                "scan_interval": 60,
                "mqtt_topic": "inverter/goodwe/stats",
            },
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["vendor"] == "goodwe"
    assert result["data"]["transport"] == "auto"


async def test_failed_flow_shows_sanitized_connection_error(hass):
    result = await _select_vendor(hass, "goodwe")
    with patch(
        "custom_components.sungrow_local.config_flow.create_driver",
        return_value=FakeDriver(error=DriverError("Unable to read inverter")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "goodwe.invalid",
                "transport": "auto",
                "port": 0,
                "scan_interval": 60,
                "mqtt_topic": "inverter/goodwe/stats",
            },
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_builds_sensors_from_driver_metadata(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-installation",
        data={
            "vendor": "goodwe",
            "host": "goodwe.invalid",
            "transport": "auto",
            "scan_interval": 60,
            "mqtt_topic": "",
        },
        title="GoodWe Local",
    )
    entry.add_to_hass(hass)
    driver = FakeDriver()
    with patch(
        "custom_components.sungrow_local.coordinator.create_driver",
        return_value=driver,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    power = next(
        state
        for state in hass.states.async_all("sensor")
        if state.attributes.get("friendly_name", "").endswith("AC output power")
    )
    assert power.state == "4200"
    assert power.attributes["unit_of_measurement"] == "W"


async def test_options_enforce_conservative_interval_and_mqtt_topic(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "inverter.invalid"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"scan_interval": 60, "mqtt_topic": "inverter/stats"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 60


async def test_invalid_sungrow_protocol_key_does_not_connect(hass):
    result = await _select_vendor(hass, "sungrow")
    with patch(
        "custom_components.sungrow_local.config_flow.create_driver",
        Mock(),
    ) as create:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "inverter.invalid",
                "port": 502,
                "unit": 1,
                "scan_interval": 60,
                "mqtt_topic": "",
                "protocol_key": "not-hex",
            },
        )
    assert result["errors"] == {"protocol_key": "invalid_key"}
    create.assert_not_called()
