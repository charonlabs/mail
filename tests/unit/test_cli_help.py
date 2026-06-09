# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from __future__ import annotations

import pytest
from mail_client.admin_panel import build_parser as build_admin_parser
from mail_client.cli import build_parser as build_mail_parser
from mail_daemon.cli import build_parser as build_daemon_parser
from mail_server.cli import build_parser as build_server_parser


def test_mail_help_uses_categorized_command_sections() -> None:
    help_text = build_mail_parser().format_help()

    assert "Commands:\n  Utility:" in help_text
    assert "  Messaging:" in help_text
    assert "  Swarms:" in help_text
    assert "  Mailing Lists:" in help_text
    assert "{ping,p,login" not in help_text
    assert 'mail compose "Status update"' in help_text


def test_mail_admin_help_uses_categorized_command_sections() -> None:
    help_text = build_admin_parser().format_help()

    assert "Commands:\n  Utility:" in help_text
    assert "  Agents:" in help_text
    assert "  Daemons:" in help_text
    assert "  Webhooks:" in help_text
    assert "  Mailing Lists:" in help_text
    assert "{ping,p,login" not in help_text
    assert "mail-admin agent-list" in help_text


def test_mail_admin_subcommand_help_uses_admin_prog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_admin_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["ping", "--help"])

    assert exc_info.value.code == 0
    assert "usage: mail-admin ping" in capsys.readouterr().out


def test_mail_server_help_does_not_import_runtime_configuration() -> None:
    help_text = build_server_parser().format_help()

    assert "usage: mail-server [option]..." in help_text
    assert "--host HOST" in help_text
    assert "mail-server --host 0.0.0.0 --port 8865" in help_text


def test_mail_daemon_help_has_readable_log_options() -> None:
    help_text = build_daemon_parser().format_help()

    assert "--log-level-file LEVEL" in help_text
    assert "-llf LEVEL, -log-level-file LEVEL" not in help_text
    assert "--log-level-console LEVEL" in help_text
    assert "mail-daemon --log-level-console debug" in help_text
