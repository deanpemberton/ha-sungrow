"""Synthetic tests for the inverter driver boundary."""

from unittest.mock import AsyncMock, patch

from custom_components.sungrow_local.driver import SungrowSG5KDDriver, create_driver


def test_factory_builds_sungrow_driver_with_metadata():
    driver = create_driver({"host": "inverter.invalid"})
    assert isinstance(driver, SungrowSG5KDDriver)
    assert driver.metadata.manufacturer == "Sungrow"
    assert driver.metadata.model == "SG5K-D"


async def test_sungrow_driver_normalizes_transport_behind_read_interface():
    snapshot = {"ac_power": 1234.0}
    with patch(
        "custom_components.sungrow_local.driver.SungrowClient.read",
        AsyncMock(return_value=snapshot),
    ) as read:
        driver = SungrowSG5KDDriver("inverter.invalid")
        assert await driver.read() == snapshot
    read.assert_awaited_once_with()
