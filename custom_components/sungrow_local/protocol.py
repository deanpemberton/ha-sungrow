"""Bounded, read-only local transport. No embedded device secrets."""

import asyncio
import logging
import struct
from contextlib import asynccontextmanager, suppress

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)


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
    _LOGGER.debug("Encrypted reply envelope version=%d reserved=%d length=%d padding=%d", version, reserved, length, padding)
    if version != 1 or reserved != 0 or not 1 <= padding <= 16 or length < 9 or length + padding != len(frame) - 4 or (length + padding) % 16:
        raise ProtocolError("Invalid encrypted frame")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    payload = decryptor.update(frame[4:]) + decryptor.finalize()
    if payload[:2] != b"\x68\x68" or payload[length:] != b"\xff" * padding:
        raise ProtocolError("Invalid encrypted frame")
    return struct.pack(">H", transaction) + payload[2:length]


def decode_snapshot(words: list[int]) -> dict[str, float | None]:
    """Decode SG5K-D input registers 5008..5036 (protocol addresses 5007..5035)."""
    if len(words) != 29:
        raise ProtocolError("Incomplete register snapshot")

    def u16(index, scale=1):
        return None if words[index] == 0xFFFF else words[index] / scale

    def u32(index):
        value = words[index] | words[index + 1] << 16
        return None if value == 0xFFFFFFFF else value

    temperature = None if words[0] == 0x8000 else (words[0] - 65536 if words[0] >= 32768 else words[0]) / 10
    result = {"temperature": temperature, "dc_power": u32(9), "ac_power": u32(23), "frequency": u16(28, 10)}
    for tracker, index in ((1, 3), (2, 5)):
        voltage, current = u16(index, 10), u16(index + 1, 10)
        result[f"mppt{tracker}_voltage"] = voltage
        result[f"mppt{tracker}_current"] = current
        result[f"mppt{tracker}_power"] = None if voltage is None or current is None else round(voltage * current, 2)
    return result


class SungrowClient:
    """One bounded connection per poll; no writes or persistent sessions."""

    def __init__(self, host, port=502, unit=1, protocol_key=None, timeout=10):
        self.host, self.port, self.unit = host, port, unit
        self.protocol_key, self.timeout = protocol_key, timeout

    @asynccontextmanager
    async def _connection(self):
        _LOGGER.debug("Opening inverter TCP connection")
        reader, writer = await asyncio.open_connection(self.host, self.port)
        _LOGGER.debug("Inverter TCP connection established")
        try:
            yield reader, writer
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            _LOGGER.debug("Inverter TCP connection closed")

    async def _session_key(self):
        _LOGGER.debug("Starting read-only protocol key negotiation")
        async with self._connection() as (reader, writer):
            writer.write(bytes.fromhex("686800000006f7040ae70008"))
            await writer.drain()
            header = await reader.readexactly(7)
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            _LOGGER.debug("Key negotiation header transaction=%d protocol=%d length=%d unit=%d", transaction, protocol, length, unit)
            if transaction != 0x6868 or protocol != 0 or unit != 247 or not 3 <= length <= 19:
                _LOGGER.debug("Key negotiation failed header validation")
                raise ProtocolError("Invalid key negotiation reply")
            prefix = await reader.readexactly(2)
            if prefix[0] == 0x84:
                _LOGGER.debug("Key negotiation rejected with Modbus exception code=%d", prefix[1])
                raise NegotiationRejected("Key negotiation rejected by dongle")
            body = prefix + await reader.readexactly(length - 3)
            if len(body) != 18 or body[:2] != bytes([4, 16]):
                _LOGGER.debug("Key negotiation failed body validation function=%d byte_count=%d body_length=%d", body[0] if body else -1, body[1] if len(body) > 1 else -1, len(body))
                raise ProtocolError("Invalid key negotiation reply")
            public_key = body[2:]
            if public_key in (bytes(16), b"\xff" * 16):
                _LOGGER.debug("Key negotiation returned sentinel key; continuing with plain Modbus")
                return None
            _LOGGER.debug("Key negotiation succeeded; encrypted register read required")
            return bytes(a ^ b for a, b in zip(public_key, self.protocol_key, strict=True))

    async def read(self):
        """Fetch one coherent two-MPPT snapshot without leaking connection details."""
        mode = "negotiated" if self.protocol_key is not None else "plain"
        _LOGGER.debug("Starting inverter telemetry read mode=%s unit=%d", mode, self.unit)
        try:
            async with asyncio.timeout(self.timeout):
                key = await self._session_key() if self.protocol_key is not None else None
                async with self._connection() as (reader, writer):
                    request = struct.pack(">HHHBBHH", 1, 0, 6, self.unit, 4, 5007, 29)
                    encrypted = key is not None
                    _LOGGER.debug("Sending read-only input-register request start=5007 count=29 encrypted=%s", encrypted)
                    writer.write(encrypt_frame(request, key) if encrypted else request)
                    await writer.drain()
                    if encrypted:
                        envelope = await reader.readexactly(4)
                        size = envelope[2] + envelope[3]
                        _LOGGER.debug("Encrypted reply announced payload size=%d", size)
                        if size < 16 or size > 256 or size % 16:
                            _LOGGER.debug("Encrypted reply failed size validation")
                            raise ProtocolError("Invalid encrypted frame")
                        frame = decrypt_frame(envelope + await reader.readexactly(size), key, 1)
                        header, body = frame[:7], frame[7:]
                    else:
                        header = await reader.readexactly(7)
                        transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                        _LOGGER.debug("Modbus reply header transaction=%d protocol=%d length=%d unit=%d", transaction, protocol, length, unit)
                        if not 3 <= length <= 254:
                            _LOGGER.debug("Modbus reply failed length validation")
                            raise ProtocolError("Invalid Modbus length")
                        prefix = await reader.readexactly(2)
                        _LOGGER.debug("Modbus reply function=%d second_byte=%d", prefix[0], prefix[1])
                        if transaction != 1 or protocol != 0 or unit != self.unit:
                            _LOGGER.debug("Modbus reply failed transaction/protocol/unit validation")
                            raise ProtocolError("Invalid Modbus reply")
                        if prefix[0] == 0x84:
                            _LOGGER.debug("Register read rejected with Modbus exception code=%d", prefix[1])
                            raise ReadRejected("Inverter rejected register read")
                        if length != 61 or prefix != bytes([4, 58]):
                            _LOGGER.debug("Modbus reply failed expected function/byte-count validation")
                            raise ProtocolError("Invalid Modbus reply")
                        body = prefix + await reader.readexactly(length - 3)
                    transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                    _LOGGER.debug("Validating telemetry reply transaction=%d protocol=%d length=%d unit=%d body_length=%d", transaction, protocol, length, unit, len(body))
                    if transaction != 1 or protocol != 0 or unit != self.unit or length != len(body) + 1 or len(body) != 60 or body[:2] != bytes([4, 58]):
                        _LOGGER.debug("Telemetry reply failed final validation")
                        raise ProtocolError("Invalid Modbus reply")
                    snapshot = decode_snapshot(list(struct.unpack(">29H", body[2:])))
                    _LOGGER.debug("Telemetry read succeeded")
                    return snapshot
        except TimeoutError:
            _LOGGER.debug("Inverter telemetry read timed out")
            raise ProtocolError("Unable to read inverter") from None
        except asyncio.IncompleteReadError as err:
            _LOGGER.debug("Inverter closed connection early expected=%d received=%d", err.expected, len(err.partial))
            raise ProtocolError("Unable to read inverter") from None
        except OSError as err:
            _LOGGER.debug("Inverter TCP operation failed error_type=%s", type(err).__name__)
            raise ProtocolError("Unable to read inverter") from None
        except (ValueError, struct.error) as err:
            _LOGGER.debug("Inverter reply could not be decoded error_type=%s", type(err).__name__)
            raise ProtocolError("Unable to read inverter") from None
