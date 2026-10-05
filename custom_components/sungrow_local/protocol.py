"""Bounded, read-only local transport. No embedded device secrets."""

import asyncio
import logging
import struct
from contextlib import asynccontextmanager, suppress

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

SUNGROW_DEFAULT_PRIVATE_KEY = b"Grow#0*2Sun68CbE"


class ProtocolError(Exception):
    """Communication or malformed data; messages contain no device details."""


class NegotiationRejected(ProtocolError):
    """The dongle explicitly rejected the read-only key negotiation."""


class ReadRejected(ProtocolError):
    """The device returned a Modbus exception to a register read."""


def encrypt_frame(payload: bytes, key: bytes) -> bytes:
    """Encode the legacy dongle envelope with a caller-supplied key."""
    padding = 16 - len(payload) % 16
    plaintext = b"\x68\x68" + payload[2:] + b"\xff" * padding
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return bytes([1, 0, len(payload), padding]) + encryptor.update(plaintext) + encryptor.finalize()


def decrypt_frame(frame: bytes, key: bytes, transaction: int) -> bytes:
    """Validate the envelope before returning a Modbus frame."""
    if len(frame) < 4:
        raise ProtocolError("Invalid encrypted frame")
    version, reserved, length, padding = frame[:4]
    _LOGGER.warning("Encrypted reply envelope version=%d reserved=%d length=%d padding=%d", version, reserved, length, padding)
    if version != 1 or reserved != 0 or not 1 <= padding <= 16 or length < 9 or length + padding != len(frame) - 4 or (length + padding) % 16:
        raise ProtocolError("Invalid encrypted frame")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    payload = decryptor.update(frame[4:]) + decryptor.finalize()
    if payload[:2] != b"\x68\x68" or payload[length:] != b"\xff" * padding:
        raise ProtocolError("Invalid encrypted frame")
    return struct.pack(">H", transaction) + payload[2:length]


def decode_registers(registers: dict[int, int]) -> dict[str, float | None]:
    """Decode the small SG5K-D register blocks used by this integration."""

    def u16(register, scale=1):
        value = registers[register]
        return None if value == 0xFFFF else value / scale

    def u32(register):
        low = registers[register]
        high = registers[register + 1]
        value = low | high << 16
        return None if value == 0xFFFFFFFF else value

    temp_raw = registers[5008]
    temperature = (
        None
        if temp_raw == 0x8000
        else (temp_raw - 65536 if temp_raw >= 32768 else temp_raw) / 10
    )

    result = {
        "temperature": temperature,
        "dc_power": u32(5017),
        "ac_power": u32(5031),
        "frequency": u16(5036, 10),
    }
    for tracker, voltage_reg, current_reg in (
        (1, 5011, 5012),
        (2, 5013, 5014),
    ):
        voltage = u16(voltage_reg, 10)
        current = u16(current_reg, 10)
        result[f"mppt{tracker}_voltage"] = voltage
        result[f"mppt{tracker}_current"] = current
        result[f"mppt{tracker}_power"] = (
            None if voltage is None or current is None else round(voltage * current, 2)
        )
    return result


class SungrowClient:
    """One bounded connection per poll; no writes or persistent sessions."""

    def __init__(self, host, port=502, unit=1, protocol_key=None, timeout=10):
        self.host, self.port, self.unit = host, port, unit
        self.protocol_key = protocol_key or SUNGROW_DEFAULT_PRIVATE_KEY
        self.timeout = timeout

    @asynccontextmanager
    async def _connection(self):
        _LOGGER.warning("Opening inverter TCP connection")
        reader, writer = await asyncio.open_connection(self.host, self.port)
        _LOGGER.warning("Inverter TCP connection established")
        try:
            yield reader, writer
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            _LOGGER.warning("Inverter TCP connection closed")

    async def _session_key(self):
        _LOGGER.warning("Starting read-only protocol key negotiation")
        async with self._connection() as (reader, writer):
            writer.write(bytes.fromhex("686800000006f7040ae70008"))
            await writer.drain()
            header = await reader.readexactly(7)
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            _LOGGER.warning("Key negotiation header transaction=%d protocol=%d length=%d unit=%d", transaction, protocol, length, unit)
            if transaction != 0x6868 or protocol != 0 or unit != 247 or not 3 <= length <= 19:
                _LOGGER.warning("Key negotiation failed header validation")
                raise ProtocolError("Invalid key negotiation reply")
            prefix = await reader.readexactly(2)
            if prefix[0] == 0x84:
                _LOGGER.warning("Key negotiation rejected with Modbus exception code=%d", prefix[1])
                raise NegotiationRejected("Key negotiation rejected by dongle")
            body = prefix + await reader.readexactly(length - 3)
            if len(body) != 18 or body[:2] != bytes([4, 16]):
                _LOGGER.warning("Key negotiation failed body validation function=%d byte_count=%d body_length=%d", body[0] if body else -1, body[1] if len(body) > 1 else -1, len(body))
                raise ProtocolError("Invalid key negotiation reply")
            public_key = body[2:]
            if public_key in (bytes(16), b"\xff" * 16):
                _LOGGER.warning("Key negotiation returned sentinel key; continuing with plain Modbus")
                return None
            _LOGGER.warning("Key negotiation succeeded; encrypted register read required")
            return bytes(a ^ b for a, b in zip(public_key, self.protocol_key, strict=True))

    async def _read_block(self, start: int, count: int, key: bytes | None):
        """Read one small FC04 block.

        Sungrow SG5K-D firmware can reject a large contiguous span even when
        the individual registers are valid, so keep requests narrowly scoped.
        """
        async with self._connection() as (reader, writer):
            request = struct.pack(">HHHBBHH", 1, 0, 6, self.unit, 4, start - 1, count)
            encrypted = key is not None
            _LOGGER.warning(
                "Sending FC04 block register=%d count=%d encrypted=%s",
                start,
                count,
                encrypted,
            )
            writer.write(encrypt_frame(request, key) if encrypted else request)
            await writer.drain()

            if encrypted:
                envelope = await reader.readexactly(4)
                size = envelope[2] + envelope[3]
                _LOGGER.warning("Encrypted reply announced payload size=%d", size)
                if size < 16 or size > 256 or size % 16:
                    raise ProtocolError("Invalid encrypted frame")
                frame = decrypt_frame(
                    envelope + await reader.readexactly(size), key, 1
                )
                header, body = frame[:7], frame[7:]
            else:
                header = await reader.readexactly(7)
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                _LOGGER.warning(
                    "Modbus reply header transaction=%d protocol=%d length=%d unit=%d",
                    transaction,
                    protocol,
                    length,
                    unit,
                )
                if not 3 <= length <= 254:
                    raise ProtocolError("Invalid Modbus length")
                prefix = await reader.readexactly(2)
                _LOGGER.warning(
                    "Modbus reply function=%d second_byte=%d",
                    prefix[0],
                    prefix[1],
                )
                if transaction != 1 or protocol != 0 or unit != self.unit:
                    raise ProtocolError("Invalid Modbus reply")
                if prefix[0] == 0x84:
                    _LOGGER.warning(
                        "Register block rejected register=%d count=%d exception=%d",
                        start,
                        count,
                        prefix[1],
                    )
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
        """Fetch the required SG5K-D telemetry using small safe FC04 blocks."""
        mode = "auto-negotiated"
        _LOGGER.warning(
            "Starting inverter telemetry read mode=%s unit=%d", mode, self.unit
        )
        try:
            async with asyncio.timeout(self.timeout):
                key = await self._session_key()
                registers: dict[int, int] = {}
                for start, count in (
                    (5008, 1),
                    (5011, 4),
                    (5017, 2),
                    (5031, 2),
                    (5036, 1),
                ):
                    words = await self._read_block(start, count, key)
                    for offset, value in enumerate(words):
                        registers[start + offset] = value
                snapshot = decode_registers(registers)
                _LOGGER.warning("Telemetry read succeeded")
                return snapshot
        except TimeoutError:
            _LOGGER.warning("Inverter telemetry read timed out")
            raise ProtocolError("Unable to read inverter") from None
        except asyncio.IncompleteReadError as err:
            _LOGGER.warning(
                "Inverter closed connection early expected=%d received=%d",
                err.expected,
                len(err.partial),
            )
            raise ProtocolError("Unable to read inverter") from None
        except OSError as err:
            _LOGGER.warning(
                "Inverter TCP operation failed error_type=%s", type(err).__name__
            )
            raise ProtocolError("Unable to read inverter") from None
        except (ValueError, struct.error) as err:
            _LOGGER.warning(
                "Inverter reply could not be decoded error_type=%s",
                type(err).__name__,
            )
            raise ProtocolError("Unable to read inverter") from None

