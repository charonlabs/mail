# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Tiny TLS reverse proxy used only by the federation E2E test harness."""

from __future__ import annotations

import http.client
import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/__proxy_health":
            self._reply(200, b"ok", {"Content-Type": "text/plain"})
            return
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward()

    def _forward(self) -> None:
        authority = self.headers.get("Host", "")
        host = authority.rsplit(":", 1)[0]
        target = self.server.routes.get(host)  # type: ignore[attr-defined]
        if target is None:
            self._reply(502, b"unknown proxy authority")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, b"invalid content length")
            return
        body = self.rfile.read(content_length)
        connection = http.client.HTTPConnection(*target, timeout=10)
        try:
            connection.putrequest(
                self.command,
                self.path,
                skip_host=True,
                skip_accept_encoding=True,
            )
            for name, value in self.headers.items():
                if name.lower() not in _HOP_BY_HOP:
                    connection.putheader(name, value)
            connection.endheaders(body)
            response = connection.getresponse()
            response_body = response.read()
            headers = {
                name: value
                for name, value in response.getheaders()
                if name.lower() not in _HOP_BY_HOP | {"content-length"}
            }
            self._reply(response.status, response_body, headers)
        except OSError:
            self._reply(502, b"upstream unavailable")
        finally:
            connection.close()

    def _reply(
        self,
        status: int,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    bind_port = int(os.environ["MAIL_TEST_PROXY_PORT"])
    routes = {
        host: (target[0], int(target[1]))
        for host, target in json.loads(os.environ["MAIL_TEST_PROXY_ROUTES"]).items()
    }
    server = ThreadingHTTPServer(("0.0.0.0", bind_port), ProxyHandler)
    server.routes = routes  # type: ignore[attr-defined]
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        os.environ["MAIL_TEST_PROXY_CERT"],
        os.environ["MAIL_TEST_PROXY_KEY"],
    )
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
