# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
E2E harness: real `mail-server` and `mail-daemon` subprocesses against
a tmp-HOME deployment provisioned by `backend-init`, driven through
the `mail` CLI. Excluded from default runs; select with `-m e2e`.
"""

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

VENV_BIN = Path(sys.executable).parent

HOST = "localhost"
SWARM = "chorus"
ADMIN = f"admin:root@{HOST}"
USER = f"user:alice@{HOST}"
OTHER_USER = f"user:bob@{HOST}"
AGENT = f"sage@{SWARM}@{HOST}"
DAEMON = f"daemon:dummy@{HOST}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class E2EStack:
    """One provisioned deployment plus a running mail-server process."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.env = {
            **os.environ,
            "HOME": str(home),
            "MAIL_HOST": HOST,
            "MAIL_JWT_SECRET_KEY": "e2e-secret",
            "MAIL_JWT_ALGORITHM": "HS256",
            "MAIL_JWT_EXPIRE_MINUTES": "15",
        }
        self.server: subprocess.Popen | None = None
        self.credentials: dict[str, str] = {}

    # ─── provisioning and lifecycle ────────────────────────────────

    def provision(self) -> None:
        subprocess.run(
            [
                str(VENV_BIN / "backend-init"),
                "--swarm",
                SWARM,
                "--host",
                HOST,
                "--agents",
                "sage",
                "--users",
                "alice",
                "bob",
                "--admins",
                "root",
                "--daemons",
                "dummy",
            ],
            env=self.env,
            check=True,
            capture_output=True,
        )
        secrets_dir = (
            self.home / ".mail-swarms" / "deployments" / "default" / ".secrets"
        )
        self.credentials = {
            path.name: path.read_text().strip() for path in secrets_dir.iterdir()
        }

    def start_server(
        self,
        timeout: float = 20.0,
        memory_save_interval: float | None = None,
    ) -> None:
        command = [
            str(VENV_BIN / "mail-server"),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        if memory_save_interval is not None:
            command.extend(["--memory-save-interval", str(memory_save_interval)])

        self.server = subprocess.Popen(
            command,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                output = self.server.stdout.read().decode()  # type: ignore[union-attr]
                raise RuntimeError(f"mail-server exited during startup:\n{output}")
            try:
                if httpx.get(f"{self.base_url}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError("mail-server did not become healthy in time")

    def stop_server(self) -> None:
        if self.server is None:
            return
        # SIGTERM lets uvicorn run the lifespan shutdown, which persists
        # backend state to the deployment dir.
        self.server.terminate()
        self.server.wait(timeout=15)
        self.server = None

    def kill_server(self) -> None:
        if self.server is None:
            return
        self.server.kill()
        self.server.wait(timeout=15)
        self.server = None

    def restart_server(self) -> None:
        self.stop_server()
        self.start_server()

    # ─── drivers ───────────────────────────────────────────────────

    def cli(
        self, *args: str, token: str | None = None
    ) -> subprocess.CompletedProcess:
        env = {**self.env, "MAIL_SERVER": self.base_url}
        if token is not None:
            env["MAIL_TOKEN"] = token
        return subprocess.run(
            [str(VENV_BIN / "mail"), "--output", "json", *args],
            env=env,
            capture_output=True,
            text=True,
        )

    def cli_json(self, *args: str, token: str | None = None) -> dict:
        result = self.cli(*args, token=token)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def login(self, address: str, password: str | None = None) -> str:
        env = {
            **self.env,
            "MAIL_SERVER": self.base_url,
            "MAIL_ADDRESS": address,
            "MAIL_PASSWORD": password or self.credentials[address],
        }
        result = subprocess.run(
            [str(VENV_BIN / "mail"), "--output", "json", "login"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)["access_token"]

    @contextmanager
    def daemon_running(self):
        """Run a real mail-daemon; its first poll iteration is immediate."""

        env = {
            **self.env,
            "MAIL_SERVER": self.base_url,
            "MAIL_ADDRESS": DAEMON,
            "MAIL_PASSWORD": self.credentials[DAEMON],
        }
        daemon = subprocess.Popen(
            [str(VENV_BIN / "mail-daemon")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            yield daemon
        finally:
            daemon.terminate()
            daemon.wait(timeout=10)

    def wait_for(
        self, condition: Callable[[], bool], timeout: float = 20.0
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.25)
        raise TimeoutError("condition not met before timeout")


@pytest.fixture
def e2e_stack(tmp_path: Path) -> E2EStack:
    home = tmp_path / "home"
    home.mkdir()
    stack = E2EStack(home)
    stack.provision()
    stack.start_server()
    yield stack
    stack.stop_server()
