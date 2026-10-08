"""MCP transports: stdio (newline-delimited JSON) and Streamable HTTP (JSON responses)."""

from __future__ import annotations

import hmac
import json
import logging
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, BinaryIO, Iterable, Optional
from urllib.parse import urlsplit

from .protocol import PARSE_ERROR, McpServer, error_response

LOG = logging.getLogger("iso5807_mcp")
MAX_BODY_BYTES = 4 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _encode(message: Any) -> bytes:
    # ASCII-only JSON never contains a raw newline, so one message is one line.
    return json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def serve_stdio(server: McpServer, stdin: Optional[BinaryIO] = None,
                stdout: Optional[BinaryIO] = None) -> None:
    """Serve MCP over stdio until the client closes stdin."""
    reader = stdin or sys.stdin.buffer
    writer = stdout or sys.stdout.buffer
    LOG.info("serving MCP on stdio")
    for raw in iter(reader.readline, b""):
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            response: Any = error_response(None, PARSE_ERROR, f"Parse error: {exc}")
        else:
            response = server.handle(message)
        if response is not None:
            writer.write(_encode(response) + b"\n")
            writer.flush()


class _Handler(BaseHTTPRequestHandler):
    server_version = "iso5807-mcp"
    protocol_version = "HTTP/1.1"

    # -- helpers ---------------------------------------------------------------
    @property
    def cfg(self) -> "McpHttpServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: Any) -> None:  # route access log to logging
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _path(self) -> str:
        return urlsplit(self.path).path.rstrip("/") or "/"

    def _send(self, status: int, body: bytes = b"", content_type: str = "application/json",
              headers: Iterable[tuple] = ()) -> None:
        self.send_response(status)
        if body:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: Any, headers: Iterable[tuple] = ()) -> None:
        self._send(status, _encode(payload), headers=headers)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # not a browser request
        if origin in self.cfg.allowed_origins or "*" in self.cfg.allowed_origins:
            return True
        host = urlsplit(origin).hostname or ""
        return host in LOCAL_HOSTS and self.cfg.allow_local_origins

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and self._origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")

    def _authorized(self) -> bool:
        token = self.cfg.auth_token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(supplied.strip(), token)

    def _guard(self) -> bool:
        if self._path() != self.cfg.mcp_path:
            self._send_json(404, {"error": "not found"})
            return False
        if not self._origin_allowed():
            self._send_json(403, {"error": "origin not allowed"})
            return False
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"},
                            headers=[("WWW-Authenticate", "Bearer")])
            return False
        return True

    # -- methods ---------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        if not self._guard():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length <= 0:
            self._send_json(400, error_response(None, PARSE_ERROR, "Empty or invalid body"))
            return
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request body too large"})
            return
        body = self.rfile.read(length)
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, error_response(None, PARSE_ERROR, f"Parse error: {exc}"))
            return
        response = self.cfg.mcp.handle(message)
        if response is None:  # notifications and responses only
            self._send(202)
        else:
            self._send_json(200, response)

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/healthz":
            self._send_json(200, {"status": "ok", "server": self.cfg.mcp.name,
                                  "version": self.cfg.mcp.version})
        elif path == self.cfg.mcp_path:
            # No server-initiated SSE stream is offered (allowed by the spec).
            self._send(405, headers=[("Allow", "POST, OPTIONS")])
        else:
            self._send_json(404, {"error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        if self._path() == self.cfg.mcp_path:
            self._send(405, headers=[("Allow", "POST, OPTIONS")])  # stateless: no sessions
        else:
            self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._path() != self.cfg.mcp_path or not self._origin_allowed():
            self._send(403)
            return
        self._send(204, headers=[
            ("Access-Control-Allow-Methods", "POST, GET, DELETE, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, "
             "Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID"),
            ("Access-Control-Max-Age", "600"),
        ])


class McpHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, mcp: McpServer, host: str = "127.0.0.1", port: int = 8765,
                 mcp_path: str = "/mcp", allowed_origins: Iterable[str] = (),
                 auth_token: Optional[str] = None, allow_local_origins: bool = True) -> None:
        self.mcp = mcp
        self.mcp_path = "/" + mcp_path.strip("/") if mcp_path.strip("/") else "/"
        self.allowed_origins = set(allowed_origins)
        self.auth_token = auth_token or None
        self.allow_local_origins = allow_local_origins
        if ":" in host:
            self.address_family = socket.AF_INET6
        super().__init__((host, port), _Handler)


def serve_http(mcp: McpServer, host: str, port: int, mcp_path: str = "/mcp",
               allowed_origins: Iterable[str] = (), auth_token: Optional[str] = None) -> None:
    httpd = McpHttpServer(mcp, host, port, mcp_path, allowed_origins, auth_token)
    bound_host, bound_port = httpd.server_address[:2]
    print(f"{mcp.title} {mcp.version}: Streamable HTTP endpoint "
          f"http://{bound_host}:{bound_port}{httpd.mcp_path}", file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
