# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
CLI / server wiring for the sqlite backend: the ``--backend sqlite`` flag, its
``--sqlite-path`` / ``--database-url`` options (with env fallbacks), the URL
resolution precedence, and that ``run_server`` actually constructs a
``SQLiteBackend``.
"""

import os
from argparse import Namespace
from pathlib import Path

import pytest

# server.py reads MAIL_HOST and routers.auth reads MAIL_JWT_EXPIRE_MINUTES at
# import time.
os.environ.setdefault("MAIL_HOST", "localhost")
os.environ.setdefault("MAIL_JWT_EXPIRE_MINUTES", "15")

from mail_server import server as server_module  # noqa: E402
from mail_server.backends.sqlite.api import SQLiteBackend  # noqa: E402
from mail_server.cli import build_parser  # noqa: E402


def test_parser_accepts_sqlite_backend_and_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["--backend", "sqlite", "--sqlite-path", "/tmp/mail.db"]
    )
    assert args.backend == "sqlite"
    assert args.sqlite_path == "/tmp/mail.db"
    assert args.database_url is None


def test_parser_reads_env_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SQLITE_PATH", "/env/path.db")
    monkeypatch.setenv("MAIL_DATABASE_URL", "sqlite:////env/url.db")
    args = build_parser().parse_args([])
    assert args.sqlite_path == "/env/path.db"
    assert args.database_url == "sqlite:////env/url.db"


def test_resolve_url_prefers_database_url() -> None:
    args = Namespace(
        database_url="sqlite:////abs/custom.db", sqlite_path="/ignored.db"
    )
    assert server_module._resolve_sqlite_url(args) == "sqlite:////abs/custom.db"


def test_resolve_url_uses_sqlite_path() -> None:
    args = Namespace(database_url=None, sqlite_path="/var/lib/mail/mail.db")
    assert (
        server_module._resolve_sqlite_url(args)
        == "sqlite:////var/lib/mail/mail.db"
    )


def test_resolve_url_falls_back_to_default() -> None:
    args = Namespace(database_url=None, sqlite_path=None)
    url = server_module._resolve_sqlite_url(args)
    assert url.startswith("sqlite:///")
    assert url.endswith("deployments/default/mail.db")


def test_run_server_constructs_sqlite_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Stub out the blocking calls so run_server just performs backend selection.
    monkeypatch.setattr(server_module, "init_logger", lambda: None)
    monkeypatch.setattr(server_module.uvicorn, "run", lambda *a, **k: None)

    args = Namespace(
        backend="sqlite",
        host="localhost",
        port=8000,
        sqlite_path=str(tmp_path / "mail.db"),
        database_url=None,
    )
    server_module.run_server(args)

    assert isinstance(server_module._backend, SQLiteBackend)
