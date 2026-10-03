"""Bounded, read-only local transport. No embedded device secrets."""

import asyncio
import struct
from contextlib import asynccontextmanager, suppress

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class ProtocolError(Exception):
    """Communication or malformed data; messages contain no device details."""


def encrypt_frame(payload: bytes, key: bytes) -> bytes:
    """Encode the legacy dongle envelope with a caller-supplied key."""
    padding = 16 - len(payload) % 16
    plaintext = b"\x68\x68" + payload[2:] + b"\xff" * padding
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return (
        bytes([1, 0, len(payload), padding])
        + encryptor.update(plaintext)
        + encryptor.finalize()
    )


def decrypt_frame(frame: bytes, key: bytes, transaction: int) -> bytes:
    """Validate the envelope before returning a Modbus frame."""
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


def decode_snapshot(words: list[int]) -> dict[str, float | None]:
    """Decode SG5K-D input registers 5008..5036 (protocol addresses 5007..5035)."""
    if len(words) != 29:
        raise ProtocolError("Incomplete register snapshot")

    def u16(index, scale=1):
        return None if words[index] == 0xFFFF else words[index] / scale

    def u32(index):
        value = words[index] | words[index + 1] << 16
        return None if value == 0xFFFFFFFF else value

    temperature = (
        None
        if words[0] == 0x8000
        else (words[0] - 65536 if words[0] >= 32768 else words[0]) / 10
    )
    result = {
        "temperature": temperature,
        "dc_power": u32(9),
        "ac_power": u32(23),
        "frequency": u16(28, 10),
    }
    for tracker, index in ((1, 3), (2, 5)):
        voltage, current = u16(index, 10), u16(index + 1, 10)
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
        self.protocol_key, self.timeout = protocol_key, timeout

    @asynccontextmanager
    async def _connection(self):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            yield reader, writer
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    async def _session_key(self):
        async with self._connection() as (reader, writer):
            # Read-only key negotiation, addressed to the communication module.
            writer.write(bytes.fromhex("686800000006f7040ae70008"))
            await writer.drain()
            response = await reader.readexactly(25)
            if response[:9] != bytes.fromhex("686800000013f70410"):
                raise ProtocolError("Invalid key negotiation reply")
            public_key = response[9:]
            if public_key in (bytes(16), b"\xff" * 16):
                return None
            return bytes(
                a ^ b for a, b in zip(public_key, self.protocol_key, strict=True)
            )

    async def read(self):
        """Fetch one coherent two-MPPT snapshot without leaking connection details."""
        try:
            async with asyncio.timeout(self.timeout):
                key = (
                    await self._session_key() if self.protocol_key is not None else None
                )
                async with self._connection() as (reader, writer):
                    request = struct.pack(">HHHBBHH", 1, 0, 6, self.unit, 4, 5007, 29)
                    writer.write(
                        encrypt_frame(request, key) if key is not None else request
                    )
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
                        transaction, protocol, length, unit = struct.unpack(
                            ">HHHB", header
                        )
                        if not 3 <= length <= 254:
                            raise ProtocolError("Invalid Modbus length")
                        body = await reader.readexactly(length - 1)
                    transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                    if (
                        transaction != 1
                        or protocol != 0
                        or unit != self.unit
                        or length != len(body) + 1
                        or len(body) != 60
                        or body[:2] != bytes([4, 58])
                    ):
                        raise ProtocolError("Invalid Modbus reply")
                    return decode_snapshot(list(struct.unpack(">29H", body[2:])))
        except (
            OSError,
            TimeoutError,
            asyncio.IncompleteReadError,
            ValueError,
            struct.error,
        ):
            raise ProtocolError("Unable to read inverter") from None
