"""Home Assistant behavior with synthetic SG5K-D telemetry."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sungrow_local.const import (
    DEFAULT_INTERVAL,
    DEFAULT_MQTT_TOPIC,
    DOMAIN,
)
from custom_components.sungrow_local.protocol import ProtocolError

SNAPSHOT = {
    "nominal_active_power": 5000,
    "daily_energy": 12.3,
    "legacy_total_energy": 1000,
    "total_energy": 1234.5,
    "total_running_time": 10000,
    "daily_running_time": 360,
    "temperature": 25.5,
    "apparent_power": 4300,
    "mppt1_voltage": 320.0,
    "mppt1_current": 7.0,
    "mppt1_power": 2240.0,
    "mppt2_voltage": 350.0,
    "mppt2_current": 6.0,
    "mppt2_power": 2100.0,
    "dc_power": 4340,
    "phase_a_voltage": 230.1,
    "phase_b_voltage": 0.0,
    "phase_c_voltage": 0.0,
    "phase_a_current": 18.3,
    "phase_b_current": 0.0,
    "phase_c_current": 0.0,
    "ac_power": 4200,
    "reactive_power": 50,
    "power_factor": 0.998,
    "frequency": 50.0,
    "device_status": 1,
    "fault_code": 0,
    "nominal_reactive_power": 1000,
    "grid_power": -300,
    "house_power": 2200,
    "daily_import_energy": 1.5,
    "daily_consumption": 8.0,
    "total_consumption": 123.4,
    "negative_voltage_to_ground": 0.0,
}


async def test_config_flow_validates_and_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    with patch(
        "custom_components.sungrow_local.protocol.SungrowClient.read",
        AsyncMock(return_value=SNAPSHOT),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "inverter.invalid",
                "port": 502,
                "unit": 1,
                "scan_interval": DEFAULT_INTERVAL,
                "mqtt_topic": DEFAULT_MQTT_TOPIC,
                "protocol_key": "",
            },
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "inverter.invalid"
    assert result["data"]["scan_interval"] == 60
    assert result["data"]["mqtt_topic"] == "inverter/stats"


async def test_failed_flow_shows_sanitized_connection_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch(
        "custom_components.sungrow_local.protocol.SungrowClient.read",
        AsyncMock(side_effect=ProtocolError("Unable to read inverter")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "inverter.invalid"}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_exposes_expanded_sensors(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-installation",
        data={
            CONF_HOST: "inverter.invalid",
            "scan_interval": 60,
            "mqtt_topic": "inverter/stats",
        },
        title="Sungrow Local",
    )
    entry.add_to_hass(hass)
    read = AsyncMock(return_value=SNAPSHOT)
    with (
        patch(
            "custom_components.sungrow_local.coordinator.importlib.reload",
            lambda module: module,
        ),
        patch(
            "custom_components.sungrow_local.protocol.SungrowClient.read",
            read,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    sensor_states = hass.states.async_all("sensor")
    names = {state.attributes.get("friendly_name"): state for state in sensor_states}
    mppt = next(
        state for name, state in names.items()
        if name and name.endswith("MPPT 1 power")
    )
    total_energy = next(
        state for name, state in names.items()
        if name and name.endswith("Total energy")
    )
    assert mppt.state == "2240.0"
    assert mppt.attributes["unit_of_measurement"] == "W"
    assert total_energy.state == "1234.5"
    assert total_energy.attributes["unit_of_measurement"] == "kWh"
    sungrow_states = [
        state
        for state in sensor_states
        if state.entity_id.startswith("sensor.sungrow")
    ]
    assert len(sungrow_states) >= 20


async def test_options_enforce_conservative_interval_and_mqtt_topic(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "inverter.invalid"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"scan_interval": 60, "mqtt_topic": "inverter/stats"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 60
    assert entry.options["mqtt_topic"] == "inverter/stats"


async def test_invalid_protocol_key_does_not_connect(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch(
        "custom_components.sungrow_local.protocol.SungrowClient.read",
        AsyncMock(),
    ) as read:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "inverter.invalid", "protocol_key": "not-hex"},
        )
    assert result["errors"] == {"protocol_key": "invalid_key"}
    read.assert_not_awaited()
