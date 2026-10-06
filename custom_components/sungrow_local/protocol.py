"""Read-only Sungrow SG5K-D local transport and register decoding."""

import asyncio
import logging
import struct
from contextlib import asynccontextmanager, suppress
from datetime import date

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

SUNGROW_DEFAULT_PRIVATE_KEY = b"Grow#0*2Sun68CbE"
GET_KEY = bytes.fromhex("686800000006f7040ae70008")
READ_BLOCKS = ((5001, 100), (5101, 50))


class ProtocolError(Exception):
    """Communication or malformed data; messages contain no device details."""


class NegotiationRejected(ProtocolError):
    """The dongle explicitly rejected the read-only key negotiation."""


class ReadRejected(ProtocolError):
    """The device returned a Modbus exception to a register read."""


def encrypt_frame(payload: bytes, key: bytes) -> bytes:
    """Encode the Sungrow encrypted Modbus envelope."""
    padding = 16 - len(payload) % 16
    plaintext = b"\x68\x68" + payload[2:] + b"\xff" * padding
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return (
        bytes([1, 0, len(payload), padding])
        + encryptor.update(plaintext)
        + encryptor.finalize()
    )


def decrypt_frame(frame: bytes, key: bytes, transaction: int) -> bytes:
    """Validate and decode the Sungrow encrypted Modbus envelope."""
    if len(frame) < 4:
        raise ProtocolError("Invalid encrypted frame")
    version, reserved, length, padding = frame[:4]
    if (
        version != 1
        or reserved != 0
        or not 1 <= padding <= 16
        or length < 9
        or length + padding != len(frame) - 4
        or (length + padding) % 16
    ):
        raise ProtocolError("Invalid encrypted frame")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    payload = decryptor.update(frame[4:]) + decryptor.finalize()
    if payload[:2] != b"\x68\x68" or payload[length:] != b"\xff" * padding:
        raise ProtocolError("Invalid encrypted frame")
    return struct.pack(">H", transaction) + payload[2:length]


def decode_registers(registers: dict[int, int]) -> dict[str, float | int | None]:
    """Decode SG5K-D telemetry from the two proven Solariot register ranges."""

    def raw(register: int) -> int:
        return registers[register]

    def u16(register: int, divisor: float = 1) -> float | int | None:
        value = raw(register)
        if value == 0xFFFF:
            return None
        result = value / divisor
        return int(result) if divisor == 1 else result

    def s16(register: int, divisor: float = 1) -> float | int | None:
        value = raw(register)
        if value == 0x8000:
            return None
        if value >= 0x8000:
            value -= 0x10000
        result = value / divisor
        return int(result) if divisor == 1 else result

    def u32(register: int, divisor: float = 1) -> float | int | None:
        low, high = raw(register), raw(register + 1)
        value = low | high << 16
        if value == 0xFFFFFFFF:
            return None
        result = value / divisor
        return int(result) if divisor == 1 else result

    def s32(register: int, divisor: float = 1) -> float | int | None:
        value = u32(register)
        if value is None:
            return None
        value = int(value)
        if value >= 0x80000000:
            value -= 0x100000000
        result = value / divisor
        return int(result) if divisor == 1 else result

    pv1_voltage = u16(5011, 10)
    pv1_current = u16(5012, 10)
    pv2_voltage = u16(5013, 10)
    pv2_current = u16(5014, 10)

    meter_raw = raw(5083)
    meter_indicator = raw(5084)
    if meter_raw == 0xFFFF and meter_indicator != 0xFFFF:
        grid_power = None
    elif meter_indicator == 0xFFFF:
        grid_power = -(0xFFFF - meter_raw)
    else:
        grid_power = meter_raw

    data: dict[str, float | int | None] = {
        "nominal_active_power": None if u16(5001) is None else u16(5001) * 100,
        "daily_energy": u16(5003, 10),
        "legacy_total_energy": u32(5004),
        "total_running_time": u32(5006),
        "temperature": s16(5008, 10),
        "apparent_power": u32(5009),
        "mppt1_voltage": pv1_voltage,
        "mppt1_current": pv1_current,
        "mppt1_power": (
            None
            if pv1_voltage is None or pv1_current is None
            else round(pv1_voltage * pv1_current, 2)
        ),
        "mppt2_voltage": pv2_voltage,
        "mppt2_current": pv2_current,
        "mppt2_power": (
            None
            if pv2_voltage is None or pv2_current is None
            else round(pv2_voltage * pv2_current, 2)
        ),
        "dc_power": u32(5017),
        "phase_a_voltage": u16(5019, 10),
        "phase_b_voltage": u16(5020, 10),
        "phase_c_voltage": u16(5021, 10),
        "phase_a_current": u16(5022, 10),
        "phase_b_current": u16(5023, 10),
        "phase_c_current": u16(5024, 10),
        "ac_power": u32(5031),
        "reactive_power": s32(5033),
        "power_factor": s16(5035, 1000),
        "frequency": u16(5036, 10),
        "device_status": u16(5038),
        "fault_code": u16(5045),
        "nominal_reactive_power": (
            None if u16(5049) is None else u16(5049) * 100
        ),
        "grid_power": grid_power,
        "house_power": u16(5091),
        "daily_import_energy": u16(5097, 10),
        "daily_consumption": u16(5101, 10),
        "total_consumption": u16(5103, 10),
        "daily_running_time": u16(5113),
        "total_energy": u32(5144, 10),
        "negative_voltage_to_ground": s16(5146, 10),
    }
    return data


def mqtt_payload(snapshot: dict[str, float | int | None]) -> dict:
    """Add legacy Solariot-compatible aliases without another inverter read."""
    payload = dict(snapshot)
    payload.update(
        {
            "daily_power_yield": (
                None
                if snapshot["daily_energy"] is None
                else snapshot["daily_energy"] * 1000
            ),
            "total_power_yield": (
                None
                if snapshot["total_energy"] is None
                else snapshot["total_energy"] / 1000
            ),
            "internal_temp": snapshot["temperature"],
            "pv1_voltage": snapshot["mppt1_voltage"],
            "pv1_current": snapshot["mppt1_current"],
            "pv2_voltage": snapshot["mppt2_voltage"],
            "pv2_current": snapshot["mppt2_current"],
            "total_pv_power": snapshot["dc_power"],
            "grid_voltage": snapshot["phase_a_voltage"],
            "inverter_current": snapshot["phase_a_current"],
            "total_active_power": snapshot["ac_power"],
            "export_power": snapshot["grid_power"],
            "power_meter": snapshot["house_power"],
            "daily_purchased_energy": snapshot["daily_import_energy"],
            "daily_energy_consumption": (
                None
                if snapshot["daily_consumption"] is None
                else snapshot["daily_consumption"] * 1000
            ),
            "total_energy_consumption": snapshot["total_consumption"],
        }
    )
    return payload


class SungrowClient:
    """Rate-conscious read-only SG5K-D client."""

    def __init__(self, host, port=502, unit=1, protocol_key=None, timeout=10):
        self.host, self.port, self.unit = host, port, unit
        self.protocol_key = protocol_key or SUNGROW_DEFAULT_PRIVATE_KEY
        self.timeout = timeout
        self._cached_key: bytes | None = None
        self._cached_key_date: date | None = None

    @asynccontextmanager
    async def _connection(self):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            yield reader, writer
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    def invalidate_session_key(self) -> None:
        """Force negotiation on the next scheduled poll, never immediately retry."""
        self._cached_key = None
        self._cached_key_date = None

    async def _session_key(self) -> bytes | None:
        today = date.today()
        if self._cached_key_date == today:
            return self._cached_key

        _LOGGER.debug("Negotiating Sungrow read-only session key")
        async with self._connection() as (reader, writer):
            writer.write(GET_KEY)
            await writer.drain()
            header = await reader.readexactly(7)
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            if (
                transaction != 0x6868
                or protocol != 0
                or unit != 247
                or not 3 <= length <= 19
            ):
                raise ProtocolError("Invalid key negotiation reply")
            prefix = await reader.readexactly(2)
            if prefix[0] == 0x84:
                raise NegotiationRejected("Key negotiation rejected by dongle")
            body = prefix + await reader.readexactly(length - 3)
            if len(body) != 18 or body[:2] != bytes([4, 16]):
                raise ProtocolError("Invalid key negotiation reply")
            public_key = body[2:]
            if public_key in (bytes(16), b"\xff" * 16):
                key = None
            else:
                key = bytes(
                    a ^ b
                    for a, b in zip(public_key, self.protocol_key, strict=True)
                )
            self._cached_key = key
            self._cached_key_date = today
            return key

    async def _read_block(
        self, start: int, count: int, key: bytes | None
    ) -> list[int]:
        async with self._connection() as (reader, writer):
            request = struct.pack(
                ">HHHBBHH", 1, 0, 6, self.unit, 4, start - 1, count
            )
            writer.write(encrypt_frame(request, key) if key is not None else request)
            await writer.drain()

            if key is not None:
                envelope = await reader.readexactly(4)
                size = envelope[2] + envelope[3]
                if size < 16 or size > 256 or size % 16:
                    raise ProtocolError("Invalid encrypted frame")
                frame = decrypt_frame(
                    envelope + await reader.readexactly(size), key, 1
                )
                header, body = frame[:7], frame[7:]
            else:
                header = await reader.readexactly(7)
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                if not 3 <= length <= 254:
                    raise ProtocolError("Invalid Modbus length")
                prefix = await reader.readexactly(2)
                if transaction != 1 or protocol != 0 or unit != self.unit:
                    raise ProtocolError("Invalid Modbus reply")
                if prefix[0] == 0x84:
                    raise ReadRejected("Inverter rejected register read")
                expected_bytes = count * 2
                if prefix != bytes([4, expected_bytes]):
                    raise ProtocolError("Invalid Modbus reply")
                body = prefix + await reader.readexactly(length - 3)

            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            expected_body_len = 2 + count * 2
            if (
                transaction != 1
                or protocol != 0
                or unit != self.unit
                or length != len(body) + 1
                or len(body) != expected_body_len
                or body[:2] != bytes([4, count * 2])
            ):
                raise ProtocolError("Invalid Modbus reply")
            return list(struct.unpack(f">{count}H", body[2:]))

    async def read(self):
        """Fetch a full telemetry snapshot with two register requests per poll."""
        try:
            async with asyncio.timeout(self.timeout):
                key = await self._session_key()
                registers: dict[int, int] = {}
                for start, count in READ_BLOCKS:
                    words = await self._read_block(start, count, key)
                    for offset, value in enumerate(words):
                        registers[start + offset] = value
                return decode_registers(registers)
        except (ProtocolError, TimeoutError, asyncio.IncompleteReadError, OSError):
            self.invalidate_session_key()
            raise ProtocolError("Unable to read inverter") from None
        except (ValueError, struct.error):
            self.invalidate_session_key()
            raise ProtocolError("Unable to read inverter") from None
