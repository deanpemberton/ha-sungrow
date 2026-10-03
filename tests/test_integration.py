"""End-to-end Home Assistant behavior with synthetic telemetry."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_protocol import registers

from custom_components.sungrow_local.const import DOMAIN
from custom_components.sungrow_local.protocol import ProtocolError, decode_snapshot


async def test_config_flow_validates_before_creating_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    with patch(
        "custom_components.sungrow_local.config_flow.SungrowClient.read",
        AsyncMock(return_value=decode_snapshot(registers())),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "inverter.invalid",
                "port": 502,
                "unit": 1,
                "scan_interval": 30,
                "protocol_key": "",
            },
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "inverter.invalid"


async def test_failed_flow_shows_sanitized_connection_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch(
        "custom_components.sungrow_local.config_flow.SungrowClient.read",
        AsyncMock(side_effect=ProtocolError("Unable to read inverter")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "inverter.invalid"}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_sensors_failure_recovery_and_unload(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-installation",
        data={CONF_HOST: "inverter.invalid"},
        title="Sungrow Local",
    )
    entry.add_to_hass(hass)
    read = AsyncMock(return_value=decode_snapshot(registers()))
    with patch("custom_components.sungrow_local.protocol.SungrowClient.read", read):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        states = {
            state.attributes["friendly_name"]: state
            for state in hass.states.async_all("sensor")
        }
        mppt = next(
            state for name, state in states.items() if name.endswith("MPPT 1 power")
        )
        assert mppt.state == "2240.0"
        assert mppt.attributes["unit_of_measurement"] == "W"
        assert mppt.attributes["state_class"] == "measurement"
        coordinator = entry.runtime_data
        read.side_effect = ProtocolError("Unable to read inverter")
        await coordinator.async_refresh()
        assert hass.states.get(mppt.entity_id).state == "unavailable"
        read.side_effect = None
        await coordinator.async_refresh()
        assert hass.states.get(mppt.entity_id).state == "2240.0"
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_failure_retries(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "inverter.invalid"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.sungrow_local.protocol.SungrowClient.read",
        AsyncMock(side_effect=ProtocolError("Unable to read inverter")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == config_entries.ConfigEntryState.SETUP_RETRY


async def test_invalid_protocol_key_does_not_connect(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch(
        "custom_components.sungrow_local.config_flow.SungrowClient.read", AsyncMock()
    ) as read:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "inverter.invalid", "protocol_key": "not-hex"},
        )
    assert result["errors"] == {"protocol_key": "invalid_key"}
    read.assert_not_awaited()


async def test_duplicate_inverter_aborts(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "inverter.invalid", "unit": 1}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "inverter.invalid"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_changes_polling_interval(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "inverter.invalid"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 60}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 60


async def test_reconfigure_preserves_installation_id(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-installation",
        data={CONF_HOST: "inverter.invalid", "unit": 1},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    with (
        patch(
            "custom_components.sungrow_local.config_flow.SungrowClient.read",
            AsyncMock(return_value=decode_snapshot(registers())),
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_reload", AsyncMock()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "inverter.invalid", "unit": 1}
        )
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "synthetic-installation"
