"""Synthetic frames only; never capture real installations."""

import struct
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.sungrow_local.protocol import (
    ProtocolError,
    SungrowClient,
    decode_snapshot,
    decrypt_frame,
    encrypt_frame,
)


def registers():
    words = [0] * 29
    words[0] = 0xFFF6  # -1 C
    words[3:7] = [3200, 70, 3500, 60]
    words[9:11] = [4340, 0]
    words[23:25] = [4200, 0]
    words[28] = 500
    return words


def test_two_mppt_scaling_and_little_word_order():
    data = decode_snapshot(registers())
    assert data["mppt1_voltage"] == 320
    assert data["mppt1_current"] == 7
    assert data["mppt1_power"] == 2240
    assert data["mppt2_power"] == 2100
    assert data["dc_power"] == 4340
    assert data["ac_power"] == 4200
    assert data["temperature"] == -1
    assert data["frequency"] == 50


def test_unavailable_is_not_zero_and_zero_is_valid():
    words = registers()
    words[3] = 0xFFFF
    words[5:7] = [0, 0]
    words[9:11] = [0xFFFF, 0xFFFF]
    data = decode_snapshot(words)
    assert data["mppt1_voltage"] is None
    assert data["mppt1_power"] is None
    assert data["mppt2_power"] == 0
    assert data["dc_power"] is None


def test_truncated_snapshot_rejected():
    with pytest.raises(ProtocolError):
        decode_snapshot([0] * 25)


def test_encrypted_frame_round_trip_and_malformed_padding():
    key = bytes(range(16))  # synthetic AES key
    payload = struct.pack(">HHHBBHH", 3, 0, 6, 1, 4, 5007, 29)
    frame = encrypt_frame(payload, key)
    assert decrypt_frame(frame, key, 3) == payload
    with pytest.raises(ProtocolError):
        decrypt_frame(frame[:-1], key, 3)


@pytest.mark.parametrize(
    "mutation", ["transaction", "unit", "function", "count", "exception"]
)
async def test_invalid_modbus_replies_rejected(mutation):
    reader, writer = AsyncMock(), AsyncMock()
    writer.write = lambda _: None
    writer.close = lambda: None
    transaction, unit, function, count = 1, 1, 4, 58
    if mutation == "transaction":
        transaction = 2
    if mutation == "unit":
        unit = 2
    if mutation == "function":
        function = 3
    if mutation == "count":
        count = 50
    body = bytes([function, count]) + b"\0" * 58
    if mutation == "exception":
        body = bytes([0x84, 2])
    header = struct.pack(">HHHB", transaction, 0, len(body) + 1, unit)
    reader.readexactly.side_effect = [header, body[:2], body[2:]]
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        with pytest.raises(ProtocolError):
            await SungrowClient("inverter.invalid").read()
    writer.wait_closed.assert_awaited_once()


async def test_plain_read_only_request_and_valid_reply():
    reader, writer = AsyncMock(), AsyncMock()
    writer.write = lambda value: requests.append(value)
    writer.close = lambda: None
    requests = []
    body = bytes([4, 58]) + struct.pack(">29H", *registers())
    reader.readexactly.side_effect = [
        struct.pack(">HHHB", 1, 0, 61, 1),
        body[:2],
        body[2:],
    ]
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        result = await SungrowClient("inverter.invalid").read()
    assert requests == [struct.pack(">HHHBBHH", 1, 0, 6, 1, 4, 5007, 29)]
    assert result["mppt2_power"] == 2100
    writer.wait_closed.assert_awaited_once()


async def test_connection_error_is_sanitized():
    with patch(
        "asyncio.open_connection", AsyncMock(side_effect=OSError("private detail"))
    ):
        with pytest.raises(ProtocolError, match="Unable to read inverter") as err:
            await SungrowClient("inverter.invalid").read()
    assert "private detail" not in str(err.value)


async def test_encrypted_negotiation_then_read_uses_separate_connections():
    private = bytes(range(16))
    public = bytes(range(16, 32))
    session = bytes(a ^ b for a, b in zip(private, public, strict=True))
    reader1, writer1, reader2, writer2 = (AsyncMock() for _ in range(4))
    requests = []
    for writer in (writer1, writer2):
        writer.write = lambda data: requests.append(data)
        writer.close = lambda: None
    reader1.readexactly.side_effect = [
        bytes.fromhex("686800000013f7"),
        bytes([4, 16]),
        public,
    ]
    body = bytes([4, 58]) + struct.pack(">29H", *registers())
    response = encrypt_frame(struct.pack(">HHHB", 1, 0, 61, 1) + body, session)
    reader2.readexactly.side_effect = [response[:4], response[4:]]
    with patch(
        "asyncio.open_connection",
        AsyncMock(side_effect=[(reader1, writer1), (reader2, writer2)]),
    ):
        data = await SungrowClient("inverter.invalid", protocol_key=private).read()
    assert data["mppt1_power"] == 2240
    assert requests[0] == bytes.fromhex("686800000006f7040ae70008")
    assert decrypt_frame(requests[1], session, 1)[7] == 4
    writer1.wait_closed.assert_awaited_once()
    writer2.wait_closed.assert_awaited_once()


async def test_timeout_closes_socket():
    import asyncio

    reader, writer = AsyncMock(), AsyncMock()
    writer.write = lambda _: None
    writer.close = lambda: None

    async def blocked(_):
        await asyncio.sleep(1)

    reader.readexactly.side_effect = blocked
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        with pytest.raises(ProtocolError):
            await SungrowClient("inverter.invalid", timeout=0.01).read()
    writer.wait_closed.assert_awaited_once()


async def test_short_negotiation_exception_fails_without_waiting_for_25_bytes():
    reader, writer = AsyncMock(), AsyncMock()
    writer.write = lambda _: None
    writer.close = lambda: None
    # Synthetic Modbus exception; no installation traffic or keys.
    reader.readexactly.side_effect = [bytes.fromhex("686800000003f7"), bytes([0x84, 2])]
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        with pytest.raises(ProtocolError, match="Key negotiation rejected"):
            await SungrowClient(
                "inverter.invalid", protocol_key=bytes(range(16))
            ).read()
    assert reader.readexactly.await_args_list[0].args == (7,)
    assert reader.readexactly.await_args_list[1].args == (2,)
    writer.wait_closed.assert_awaited_once()


async def test_legacy_exception_with_wrong_length_does_not_wait_for_missing_bytes():
    reader, writer = AsyncMock(), AsyncMock()
    writer.write = lambda _: None
    writer.close = lambda: None
    # Synthetic exception reproduces a legacy length-field quirk, not a capture.
    reader.readexactly.side_effect = [
        struct.pack(">HHHB", 1, 0, 6, 1),
        bytes([0x84, 4]),
    ]
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        with pytest.raises(ProtocolError, match="Inverter rejected register read"):
            await SungrowClient("inverter.invalid").read()
    assert reader.readexactly.await_args_list[1].args == (2,)
