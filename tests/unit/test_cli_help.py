# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from __future__ import annotations

from argparse import Namespace

import pytest
from mail_client.admin_panel import build_parser as build_admin_parser
from mail_client.cli import (
    _run_command,
    _text_to_markdown,
)
from mail_client.cli import (
    build_parser as build_mail_parser,
)
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


def test_mail_parser_accepts_markdown_output() -> None:
    args = build_mail_parser().parse_args(["--output", "markdown", "ping"])

    assert args.output == "markdown"


def test_text_to_markdown_converts_structured_text() -> None:
    text = (
        "=== Draft ===\n"
        "Draft ID: draft-123\n"
        "Body:\n"
        "hello world\n"
        "line: with colon\n"
        "=== Entry Data ===\n"
        "Sent At: None\n"
    )

    assert _text_to_markdown(text) == (
        "# Draft\n"
        "- **Draft ID:** draft-123\n"
        "- **Body:**\n"
        "\n"
        "```\n"
        "hello world\n"
        "line: with colon\n"
        "```\n"
        "\n"
        "## Entry Data\n"
        "- **Sent At:** None\n"
    )


def test_text_to_markdown_preserves_mailbox_summary_timestamps() -> None:
    text = (
        "=== Inbox ===\n"
        "2026-06-09T14:23:45+00:00 | msg-123 | [agent@swarm@host] Subject (42 characters)\n"
    )

    assert _text_to_markdown(text) == (
        "# Inbox\n"
        "- 2026-06-09T14:23:45+00:00 | msg-123 | [agent@swarm@host] Subject (42 characters)\n"
    )


def test_text_to_markdown_preserves_recipient_address_prefixes() -> None:
    text = (
        "=== Message ===\n"
        "Recipient(s):\n"
        "- user:alice@example.com\n"
        "- daemon:worker@example.com\n"
    )

    assert _text_to_markdown(text) == (
        "# Message\n"
        "- **Recipient(s):** \n"
        "- user:alice@example.com\n"
        "- daemon:worker@example.com\n"
    )


def test_text_to_markdown_preserves_list_addresses_and_swarm_summaries() -> None:
    text = (
        "=== Mailing Lists ===\n"
        "list:dev@example@host (3 members)\n"
        "=== Swarms ===\n"
        "[example] (2 agents): [weather, math]\n"
    )

    assert _text_to_markdown(text) == (
        "# Mailing Lists\n"
        "- list:dev@example@host (3 members)\n"
        "## Swarms\n"
        "- [example] (2 agents): [weather, math]\n"
    )


def test_run_command_renders_markdown_from_text_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def command(args: Namespace) -> None:
        assert args.output == "text"
        print("=== Inbox ===")
        print("Message ID: msg-123")

    args = Namespace(output="markdown")

    _run_command(command, args)

    assert capsys.readouterr().out == "# Inbox\n- **Message ID:** msg-123\n"
