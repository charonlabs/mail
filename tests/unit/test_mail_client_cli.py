# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest

from mail.client import MAILClientCLI


def _make_cli() -> MAILClientCLI:
    args = SimpleNamespace(url="http://example.com", api_key=None, verbose=False)
    return MAILClientCLI(args)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cli_help_does_not_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _make_cli()

    inputs = iter(["help", "exit"])
    calls: list[str] = []
    help_called = []

    def fake_input(_prompt: str) -> str:
        value = next(inputs)
        calls.append(value)
        return value

    def record_help() -> None:
        help_called.append("yes")

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.parser, "print_help", record_help)

    await cli.run()

    assert calls == ["help", "exit"]
    assert help_called == ["yes"]


@pytest.mark.asyncio
async def test_cli_handles_parse_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _make_cli()

    inputs = iter(["unknown", "exit"])
    parse_calls: list[list[str]] = []

    def fake_input(_prompt: str) -> str:
        return next(inputs)

    def fail_parse(tokens: list[str]) -> None:
        parse_calls.append(tokens)
        raise SystemExit

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.parser, "parse_args", fail_parse)

    await cli.run()

    assert parse_calls == [["unknown"]]


@pytest.mark.asyncio
async def test_cli_uses_shlex_for_tokenization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[str] = []

    async def fake_post_message(self: MAILClientCLI, args) -> None:  # type: ignore[override]
        captured_messages.append(args.body)

    monkeypatch.setattr(MAILClientCLI, "_post_message", fake_post_message)

    cli = _make_cli()

    inputs = iter(['post-message "hello world"', "exit"])

    def fake_input(_prompt: str) -> str:
        return next(inputs)

    monkeypatch.setattr(builtins, "input", fake_input)

    await cli.run()

    assert captured_messages == ["hello world"]
