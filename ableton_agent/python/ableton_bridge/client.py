from __future__ import annotations

import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class BridgeError(RuntimeError):
    pass


class BridgeTimeoutError(BridgeError):
    pass


class BridgeCommandError(BridgeError):
    def __init__(self, command: str, response: Any):
        self.command = command
        self.response = response
        message = response.get("error", response) if isinstance(response, dict) else response
        super().__init__(f"Ableton command '{command}' failed: {message}")


class AbletonBridgeClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        command_port: int = 7400,
        reply_port: int = 7401,
        timeout: float = 2.0,
    ) -> None:
        self.host = host
        self.command_port = command_port
        self.reply_port = reply_port
        self.timeout = timeout

    def request(self, command: str, payload: dict[str, Any] | None = None) -> Any:
        request_id = uuid.uuid4().hex
        payload_json = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=True)
        packet = encode_message("/agent", [request_id, command, payload_json])

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply_socket:
            reply_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reply_socket.bind((self.host, self.reply_port))
            reply_socket.settimeout(min(self.timeout, 0.2))

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as command_socket:
                command_socket.sendto(packet, (self.host, self.command_port))

            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeTimeoutError(
                        f"No reply from Max for Live on UDP {self.reply_port}; "
                        "load or reload Ableton Agent Hub.amxd in the current Set"
                    )
                reply_socket.settimeout(min(remaining, 0.2))
                try:
                    reply_packet, _address = reply_socket.recvfrom(65535)
                except socket.timeout:
                    continue
                try:
                    path, arguments = decode_message(reply_packet)
                except OscDecodeError:
                    continue
                if path != "/ableton/reply" or len(arguments) < 3:
                    continue
                response_id, ok, response_json = arguments[:3]
                if response_id != request_id:
                    continue
                try:
                    response = json.loads(response_json)
                except json.JSONDecodeError:
                    response = {"raw": response_json}
                if not ok:
                    raise BridgeCommandError(command, response)
                return response
