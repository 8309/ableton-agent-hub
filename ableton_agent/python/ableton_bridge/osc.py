from __future__ import annotations

import struct
from typing import Any


class OscDecodeError(ValueError):
    pass


def _pad_length(length: int) -> int:
    return (4 - (length % 4)) % 4


def _encode_string(value: str) -> bytes:
    encoded = value.encode("utf-8") + b"\x00"
    return encoded + b"\x00" * _pad_length(len(encoded))


def _decode_string(packet: bytes, offset: int) -> tuple[str, int]:
    try:
        end = packet.index(0, offset)
    except ValueError as error:
        raise OscDecodeError("OSC string is not null-terminated") from error
    value = packet[offset:end].decode("utf-8")
    consumed = end - offset + 1
    return value, end + 1 + _pad_length(consumed)


def encode_message(address: str, arguments: list[Any] | tuple[Any, ...] = ()) -> bytes:
    if not address.startswith("/"):
        raise ValueError("OSC address must start with '/'")

    tags = [","]
    payload = bytearray()
    for argument in arguments:
        if isinstance(argument, bool):
            tags.append("i")
            payload.extend(struct.pack(">i", int(argument)))
        elif isinstance(argument, int):
            tags.append("i")
            payload.extend(struct.pack(">i", argument))
        elif isinstance(argument, float):
            tags.append("f")
            payload.extend(struct.pack(">f", argument))
        elif isinstance(argument, str):
            tags.append("s")
            payload.extend(_encode_string(argument))
        else:
            raise TypeError(f"Unsupported OSC argument type: {type(argument).__name__}")

    return _encode_string(address) + _encode_string("".join(tags)) + bytes(payload)


def decode_message(packet: bytes) -> tuple[str, list[Any]]:
    address, offset = _decode_string(packet, 0)
    if address == "#bundle":
        raise OscDecodeError("OSC bundles are not supported")
    tags, offset = _decode_string(packet, offset)
    if not tags.startswith(","):
        raise OscDecodeError("OSC type tag string must start with ','")

    arguments: list[Any] = []
    for tag in tags[1:]:
        if tag == "i":
            if offset + 4 > len(packet):
                raise OscDecodeError("Truncated OSC int")
            arguments.append(struct.unpack_from(">i", packet, offset)[0])
            offset += 4
        elif tag == "f":
            if offset + 4 > len(packet):
                raise OscDecodeError("Truncated OSC float")
            arguments.append(struct.unpack_from(">f", packet, offset)[0])
            offset += 4
        elif tag == "s":
            value, offset = _decode_string(packet, offset)
            arguments.append(value)
        else:
            raise OscDecodeError(f"Unsupported OSC type tag: {tag}")
    return address, arguments
