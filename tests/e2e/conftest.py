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
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

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
        self.backend = "memory"
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.env = {
            **os.environ,
            "HOME": str(home),
            "MAIL_HOST": HOST,
            "MAIL_JWT_SECRET_KEY": "e2e-secret",
            "MAIL_JWT_ALGORITHM": "HS256",
            "MAIL_JWT_EXPIRE_MINUTES": "15",
            "MAIL_REFRESH_TOKEN_EXPIRE_DAYS": "30",
        }
        self.server: subprocess.Popen | None = None
        self.credentials: dict[str, str] = {}

    # ─── provisioning and lifecycle ────────────────────────────────

    def provision(self, backend: str = "memory") -> None:
        self.backend = backend
        subprocess.run(
            [
                str(VENV_BIN / "backend-init"),
                "--type",
                backend,
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
            "--backend",
            self.backend,
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

    def cli(self, *args: str, token: str | None = None) -> subprocess.CompletedProcess:
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

    def wait_for(self, condition: Callable[[], bool], timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.25)
        raise TimeoutError("condition not met before timeout")


def _write_test_ca(directory: Path) -> tuple[Path, Path, Path]:
    """Create a private CA and one localhost/loopback proxy certificate."""

    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MAIL test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    proxy_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    proxy_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "MAIL federation test proxy")]
    )
    proxy_cert = (
        x509.CertificateBuilder()
        .subject_name(proxy_name)
        .issuer_name(ca_name)
        .public_key(proxy_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.IPAddress(ip_address("127.0.0.1")),
                    x509.IPAddress(ip_address("127.0.0.2")),
                    x509.IPAddress(ip_address("127.0.0.3")),
                    x509.IPAddress(ip_address("127.0.0.4")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = directory / "ca.pem"
    cert_path = directory / "proxy-cert.pem"
    key_path = directory / "proxy-key.pem"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(proxy_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        proxy_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    return ca_path, cert_path, key_path


class FederationNode:
    """One real SQLite MAIL server participating through the TLS proxy."""

    def __init__(
        self,
        root: Path,
        *,
        name: str,
        public_host: str,
        proxy_port: int,
        ca_file: Path,
    ) -> None:
        self.name = name
        self.public_host = public_host
        self.home = root / name
        self.home.mkdir()
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.public_url = f"https://{public_host}:{proxy_port}"
        self.key_path = self.home / "federation.pem"
        self.key_id = f"{name}-key-1"
        self.log_path = self.home / "server.log"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "MAIL_HOST": public_host,
            "MAIL_JWT_SECRET_KEY": f"{name}-e2e-secret",
            "MAIL_JWT_ALGORITHM": "HS256",
            "MAIL_JWT_EXPIRE_MINUTES": "15",
            "MAIL_REFRESH_TOKEN_EXPIRE_DAYS": "30",
            "MAIL_COOKIE_SECURE": "false",
            "MAIL_FEDERATION_ENABLED": "true",
            "MAIL_FEDERATION_PUBLIC_HOST": public_host,
            "MAIL_FEDERATION_DELIVERY_URL": (
                f"{self.public_url}/daemon/deliver/remote/v1"
            ),
            "MAIL_FEDERATION_KEY_ID": self.key_id,
            "MAIL_FEDERATION_PRIVATE_KEY_FILE": str(self.key_path),
            "MAIL_FEDERATION_POLICY": "open",
            "MAIL_FEDERATION_DISCOVERY_TTL_SECONDS": "300",
            "MAIL_FEDERATION_WORKER_POLL_SECONDS": "0.05",
            "MAIL_FEDERATION_ALLOW_PRIVATE_HOSTS": "true",
            "MAIL_FEDERATION_ALLOW_INSECURE_TRANSPORT": "true",
            "MAIL_FEDERATION_TEST_DISCOVERY_PORT": str(proxy_port),
            "MAIL_FEDERATION_TEST_RETRY_DELAYS_SECONDS": "2,2,2,2,2",
            "MAIL_FEDERATION_CA_FILE": str(ca_file),
        }
        self.server: subprocess.Popen | None = None
        self.credentials: dict[str, str] = {}

    @property
    def database_path(self) -> Path:
        return self.home / ".mail-swarms/deployments/default/mail.db"

    def provision(self) -> None:
        subprocess.run(
            [
                str(VENV_BIN / "backend-init"),
                "--type",
                "sqlite",
                "--swarm",
                SWARM,
                "--host",
                self.public_host,
                "--agents",
                "sage",
                "--users",
                "alice",
                "bob",
                "--admins",
                "root",
                "--daemons",
                "dummy",
                "bounces",
            ],
            env=self.env,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                str(VENV_BIN / "mail-federation-key"),
                "generate",
                str(self.key_path),
                "--key-id",
                self.key_id,
            ],
            env=self.env,
            check=True,
            capture_output=True,
        )
        secrets_dir = self.home / ".mail-swarms/deployments/default/.secrets"
        self.credentials = {
            path.name: path.read_text().strip() for path in secrets_dir.iterdir()
        }

    def start_server(self, timeout: float = 20.0) -> None:
        command = [
            str(VENV_BIN / "mail-server"),
            "--backend",
            "sqlite",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        with self.log_path.open("ab") as output:
            self.server = subprocess.Popen(
                command,
                env=self.env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise RuntimeError(
                    f"{self.name} exited during startup:\n"
                    f"{self.log_path.read_text(errors='replace')}"
                )
            try:
                if httpx.get(f"{self.base_url}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError(f"{self.name} did not become healthy in time")

    def stop_server(self, *, kill: bool = False) -> None:
        if self.server is None:
            return
        if kill:
            self.server.kill()
        else:
            self.server.terminate()
        self.server.wait(timeout=15)
        self.server = None

    def restart_server(self) -> None:
        self.stop_server()
        self.start_server()

    def rotate_key_with_overlap(self) -> tuple[Path, str]:
        old_path = self.key_path
        old_key_id = self.key_id
        inspected = subprocess.run(
            [
                str(VENV_BIN / "mail-federation-key"),
                "inspect",
                str(old_path),
                "--key-id",
                old_key_id,
                "--json",
            ],
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        )
        overlap_path = self.home / "overlap.json"
        overlap_path.write_text(f"[{inspected.stdout.strip()}]", encoding="utf-8")
        self.key_id = f"{self.name}-key-2"
        self.key_path = self.home / "federation-2.pem"
        subprocess.run(
            [
                str(VENV_BIN / "mail-federation-key"),
                "generate",
                str(self.key_path),
                "--key-id",
                self.key_id,
            ],
            env=self.env,
            check=True,
            capture_output=True,
        )
        self.env["MAIL_FEDERATION_KEY_ID"] = self.key_id
        self.env["MAIL_FEDERATION_PRIVATE_KEY_FILE"] = str(self.key_path)
        self.env["MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS_FILE"] = str(overlap_path)
        self.restart_server()
        return old_path, old_key_id

    def remove_key_overlap(self) -> None:
        self.env.pop("MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS_FILE", None)
        self.restart_server()

    def cli(self, *args: str, token: str | None = None) -> subprocess.CompletedProcess:
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

    def login(self, user_id: str) -> str:
        address = f"user:{user_id}@{self.public_host}"
        env = {
            **self.env,
            "MAIL_SERVER": self.base_url,
            "MAIL_ADDRESS": address,
            "MAIL_PASSWORD": self.credentials[address],
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
        address = f"daemon:dummy@{self.public_host}"
        env = {
            **self.env,
            "MAIL_SERVER": self.base_url,
            "MAIL_ADDRESS": address,
            "MAIL_PASSWORD": self.credentials[address],
        }
        daemon = subprocess.Popen(
            [str(VENV_BIN / "mail-daemon")],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        try:
            yield daemon
        finally:
            daemon.terminate()
            daemon.wait(timeout=10)


class FederationE2EStack:
    """Three real nodes behind one authority-routing TLS reverse proxy."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.proxy_port = _free_port()
        self.ca_file, self.proxy_cert, self.proxy_key = _write_test_ca(root)
        self.nodes = {
            name: FederationNode(
                root,
                name=name,
                public_host=host,
                proxy_port=self.proxy_port,
                ca_file=self.ca_file,
            )
            for name, host in {
                "a": "127.0.0.2",
                "b": "127.0.0.3",
                "c": "127.0.0.4",
            }.items()
        }
        self.proxy: subprocess.Popen | None = None

    def start(self) -> None:
        for node in self.nodes.values():
            node.provision()
            node.start_server()
        routes = {
            node.public_host: ["127.0.0.1", node.port]
            for node in self.nodes.values()
        }
        env = {
            **os.environ,
            "MAIL_TEST_PROXY_PORT": str(self.proxy_port),
            "MAIL_TEST_PROXY_ROUTES": json.dumps(routes),
            "MAIL_TEST_PROXY_CERT": str(self.proxy_cert),
            "MAIL_TEST_PROXY_KEY": str(self.proxy_key),
        }
        self.proxy = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("tls_reverse_proxy.py"))],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 10
        health_url = f"https://127.0.0.1:{self.proxy_port}/__proxy_health"
        while time.monotonic() < deadline:
            if self.proxy.poll() is not None:
                raise RuntimeError("federation TLS proxy exited during startup")
            try:
                if httpx.get(health_url, verify=str(self.ca_file)).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError("federation TLS proxy did not become healthy")

    def stop(self) -> None:
        if self.proxy is not None:
            self.proxy.terminate()
            self.proxy.wait(timeout=10)
            self.proxy = None
        for node in reversed(tuple(self.nodes.values())):
            node.stop_server()

    def wait_for(self, condition: Callable[[], bool], timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.1)
        raise TimeoutError("federation condition not met before timeout")


@pytest.fixture
def e2e_stack(tmp_path: Path) -> E2EStack:
    home = tmp_path / "home"
    home.mkdir()
    stack = E2EStack(home)
    stack.provision()
    stack.start_server()
    yield stack
    stack.stop_server()


@pytest.fixture
def sqlite_e2e_stack(tmp_path: Path) -> E2EStack:
    """An e2e stack provisioned and served on the sqlite backend."""

    home = tmp_path / "home"
    home.mkdir()
    stack = E2EStack(home)
    stack.provision(backend="sqlite")
    stack.start_server()
    yield stack
    stack.stop_server()


@pytest.fixture
def federation_e2e_stack(tmp_path: Path) -> FederationE2EStack:
    stack = FederationE2EStack(tmp_path)
    stack.start()
    yield stack
    stack.stop()
