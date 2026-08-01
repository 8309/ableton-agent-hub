from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Any

from .client import AbletonBridgeClient, BridgeError


class RequestValidationError(ValueError):
    pass


def process_command_body(client: Any, body: bytes) -> Any:
    try:
        request = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestValidationError("body must be valid UTF-8 JSON") from error
    if not isinstance(request, dict):
        raise RequestValidationError("body must be a JSON object")
    command = request.get("command")
    if not isinstance(command, str) or not command:
        raise RequestValidationError("command must be a non-empty string")
    payload = request.get("payload", {})
    if not isinstance(payload, dict):
        raise RequestValidationError("payload must be a JSON object")
    return client.request(command, payload)


def make_handler(client: AbletonBridgeClient):
    class BridgeRequestHandler(BaseHTTPRequestHandler):
        server_version = "AbletonAgentBridge/0.1"

        def _json_response(self, status: int, value: Any) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json_response(200, {"ok": True, "service": "ableton-agent-bridge"})
                return
            self._json_response(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/command":
                self._json_response(404, {"ok": False, "error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise RequestValidationError("Content-Length must be between 1 and 1000000")
                result = process_command_body(client, self.rfile.read(length))
            except RequestValidationError as error:
                self._json_response(400, {"ok": False, "error": str(error)})
                return
            except BridgeError as error:
                self._json_response(502, {"ok": False, "error": str(error)})
                return
            self._json_response(200, {"ok": True, "result": result})

        def log_message(self, format_string: str, *args: Any) -> None:
            print("[%s] %s" % (self.log_date_time_string(), format_string % args))

    return BridgeRequestHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local HTTP service for Ableton Agent Hub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if args.host not in ["127.0.0.1", "localhost", "::1"]:
        raise SystemExit("Refusing to expose the bridge beyond localhost")

    client = AbletonBridgeClient(
        host="127.0.0.1",
        command_port=args.command_port,
        reply_port=args.reply_port,
        timeout=args.timeout,
    )
    server = HTTPServer((args.host, args.port), make_handler(client))
    print(f"Ableton Agent Hub bridge listening at http://{args.host}:{args.port}")
    print("POST JSON commands to /command; Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
