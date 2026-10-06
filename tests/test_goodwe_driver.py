"""Synthetic tests for the GoodWe MS G3 driver."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from goodwe.exceptions import InverterError

from custom_components.sungrow_local.goodwe_driver import GoodWeDriver


def sensor(sensor_id, name, unit=""):
    return SimpleNamespace(id_=sensor_id, name=name, unit=unit)


def fake_inverter():
    inverter = SimpleNamespace()
    inverter.model_name = "GW8500-MS-30"
    inverter.sensors = lambda: (
        sensor("vpv1", "PV1 Voltage", "V"),
        sensor("ipv1", "PV1 Current", "A"),
        sensor("ppv1", "PV1 Power", "W"),
        sensor("vpv2", "PV2 Voltage", "V"),
        sensor("ipv2", "PV2 Current", "A"),
        sensor("ppv2", "PV2 Power", "W"),
        sensor("vpv3", "PV3 Voltage", "V"),
        sensor("ipv3", "PV3 Current", "A"),
        sensor("ppv3", "PV3 Power", "W"),
        sensor("total_input_power", "Total Input Power", "W"),
        sensor("total_inverter_power", "Total Power", "W"),
        sensor("temperature", "Inverter Temperature", "C"),
        sensor("temperature_heatsink", "Heatsink Temperature", "C"),
        sensor("e_day", "Today's PV Generation", "kWh"),
        sensor("e_total", "Total PV Generation", "kWh"),
        sensor("derating_mode_label", "Derating Mode"),
        sensor("rssi", "RSSI"),
        sensor("meter_active_power", "Meter Active Power", "W"),
        sensor("meter_e_total_exp", "Meter Total Energy export", "kWh"),
        sensor("meter_e_total_imp", "Meter Total Energy import", "kWh"),
        sensor("house_consumption", "House Consumption", "W"),
    )
    inverter.read_runtime_data = AsyncMock(
        return_value={
            "vpv1": 310.1,
            "ipv1": 5.1,
            "ppv1": 1582,
            "vpv2": 320.2,
            "ipv2": 6.2,
            "ppv2": 1985,
            "vpv3": 330.3,
            "ipv3": 7.3,
            "ppv3": 2411,
            "ppv": 5978,
            "total_input_power": 5950,
            "total_inverter_power": 5700,
            "temperature": 42.1,
            "temperature_heatsink": 46.4,
            "e_day": 18.2,
            "e_total": 12345.6,
            "derating_mode_label": "None",
            "rssi": 72,
            "meter_active_power": -1200,
            "meter_e_total_exp": 2345.6,
            "meter_e_total_imp": 456.7,
            "house_consumption": 4500,
        }
    )
    return inverter


async def test_ms_g3_exposes_three_mppts_and_meter_data():
    inverter = fake_inverter()
    with patch(
        "custom_components.sungrow_local.goodwe_driver.goodwe.connect",
        AsyncMock(return_value=inverter),
    ) as connect:
        driver = GoodWeDriver("inverter.invalid", transport="auto")
        data = await driver.read()

    assert data["mppt1_power"] == 1582
    assert data["mppt2_power"] == 1985
    assert data["mppt3_power"] == 2411
    assert data["dc_power"] == 5950
    assert data["ac_power"] == 5700
    assert data["grid_power"] == -1200
    assert data["house_power"] == 4500
    assert data["total_export_energy"] == 2345.6
    assert data["total_import_energy"] == 456.7
    assert data["goodwe_temperature_heatsink"] == 46.4
    assert data["goodwe_derating_mode_label"] == "None"
    assert driver.metadata.model == "GW8500-MS-30"
    assert any(spec.key == "mppt3_voltage" for spec in driver.sensor_specs)
    assert any(
        spec.key == "total_export_energy" for spec in driver.sensor_specs
    )
    connect.assert_awaited_once()


async def test_auto_transport_falls_back_from_udp_to_modbus_tcp():
    inverter = fake_inverter()
    connect = AsyncMock(
        side_effect=[InverterError("udp unavailable"), inverter]
    )
    with patch(
        "custom_components.sungrow_local.goodwe_driver.goodwe.connect", connect
    ):
        driver = GoodWeDriver("inverter.invalid", transport="auto")
        await driver.read()

    assert connect.await_count == 2
    assert connect.await_args_list[0].kwargs["port"] == 8899
    assert connect.await_args_list[1].kwargs["port"] == 502
    assert driver.mqtt_payload({})["_transport_port"] == 502


async def test_selected_transport_is_cached_between_polls():
    inverter = fake_inverter()
    connect = AsyncMock(return_value=inverter)
    with patch(
        "custom_components.sungrow_local.goodwe_driver.goodwe.connect", connect
    ):
        driver = GoodWeDriver("inverter.invalid", transport="tcp")
        await driver.read()
        await driver.read()

    connect.assert_awaited_once()
    assert inverter.read_runtime_data.await_count == 2
