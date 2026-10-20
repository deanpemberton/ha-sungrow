"""Synthetic SG5K-D protocol tests; never use installation captures."""

import struct
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.sungrow_local.protocol import (
    ProtocolError,
    SungrowClient,
    decode_registers,
    decrypt_frame,
    encrypt_frame,
    mqtt_payload,
)


def register_map():
    regs = {register: 0 for register in range(5001, 5151)}
    regs.update(
        {
            5001: 50,
            5003: 123,
            5008: 255,
            5011: 3200,
            5012: 70,
            5013: 3500,
            5014: 60,
            5017: 4340,
            5018: 0,
            5019: 2301,
            5022: 183,
            5031: 4200,
            5032: 0,
            5035: 998,
            5036: 500,
            5038: 1,
            5045: 0,
            5083: 500,
            5084: 0,
            5091: 2200,
            5097: 15,
            5101: 80,
            5103: 1234,
            5113: 360,
            5144: 1000,
            5145: 0,
        }
    )
    return regs


def block(regs, start, count):
    return [regs[start + offset] for offset in range(count)]


def test_decode_comprehensive_snapshot():
    data = decode_registers(register_map())
    assert data["nominal_active_power"] == 5000
    assert data["daily_energy"] == 12.3
    assert data["temperature"] == 25.5
    assert data["mppt1_power"] == 2240
    assert data["mppt2_power"] == 2100
    assert data["dc_power"] == 4340
    assert data["ac_power"] == 4200
    assert data["phase_a_voltage"] == 230.1
    assert data["phase_a_current"] == 18.3
    assert data["power_factor"] == 0.998
    assert data["frequency"] == 50
    assert data["grid_power"] == 500
    assert data["house_power"] == 2200
    assert data["daily_import_energy"] == 1.5
    assert data["daily_consumption"] == 8
    assert data["total_consumption"] == 123.4
    assert data["total_energy"] == 100


def test_legacy_mqtt_aliases_from_same_snapshot():
    payload = mqtt_payload(decode_registers(register_map()))
    assert payload["daily_power_yield"] == 12300
    assert payload["total_power_yield"] == 0.1
    assert payload["internal_temp"] == 25.5
    assert payload["pv1_voltage"] == 320
    assert payload["total_pv_power"] == 4340
    assert payload["total_active_power"] == 4200
    assert payload["power_meter"] == 2200


def test_encrypted_frame_round_trip():
    key = bytes(range(16))
    payload = struct.pack(">HHHBBHH", 3, 0, 6, 1, 4, 5000, 100)
    frame = encrypt_frame(payload, key)
    assert decrypt_frame(frame, key, 3) == payload
    with pytest.raises(ProtocolError):
        decrypt_frame(frame[:-1], key, 3)


async def test_read_uses_only_two_blocks_and_caches_session_key():
    regs = register_map()
    client = SungrowClient("inverter.invalid")
    key = bytes(range(16))
    client._session_key = AsyncMock(return_value=key)
    client._read_block = AsyncMock(
        side_effect=[
            block(regs, 5001, 100),
            block(regs, 5101, 50),
            block(regs, 5001, 100),
            block(regs, 5101, 50),
        ]
    )
    first = await client.read()
    second = await client.read()
    assert first["ac_power"] == second["ac_power"] == 4200
    assert client._read_block.await_args_list[0].args[:2] == (5001, 100)
    assert client._read_block.await_args_list[1].args[:2] == (5101, 50)
    assert client._read_block.await_count == 4


async def test_connection_error_is_sanitized_and_invalidates_key():
    client = SungrowClient("inverter.invalid")
    client._cached_key = bytes(range(16))
    with patch(
        "asyncio.open_connection",
        AsyncMock(side_effect=OSError("private detail")),
    ):
        with pytest.raises(ProtocolError, match="Unable to read inverter") as err:
            await client.read()
    assert "private detail" not in str(err.value)
    assert client._cached_key is None
