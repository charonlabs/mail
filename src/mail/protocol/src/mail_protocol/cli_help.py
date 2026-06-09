# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from __future__ import annotations

import argparse
from collections.abc import Sequence

CommandHelp = tuple[str, str]
CommandGroup = tuple[str, Sequence[CommandHelp]]


class MAILHelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawDescriptionHelpFormatter,
):
    """Readable defaults for MAIL command-line help."""

    def __init__(self, prog: str):
        super().__init__(prog, max_help_position=32, width=100)


def build_epilog(
    *,
    command_groups: Sequence[CommandGroup] | None = None,
    examples: Sequence[str] | None = None,
    footer: str | None = "Copyright (c) 2026 Addison Kline",
) -> str | None:
    sections: list[str] = []

    if command_groups:
        lines = ["Commands:"]
        for title, commands in command_groups:
            lines.append(f"  {title}:")
            width = max(len(name) for name, _description in commands)
            for name, description in commands:
                lines.append(f"    {name.ljust(width)}  {description}")
        sections.append("\n".join(lines))

    if examples:
        lines = ["Examples:"]
        lines.extend(f"  {example}" for example in examples)
        sections.append("\n".join(lines))

    if footer:
        sections.append(footer)

    if not sections:
        return None

    return "\n\n".join(sections)


def make_arg_parser(
    *,
    prog: str,
    usage: str,
    description: str,
    command_groups: Sequence[CommandGroup] | None = None,
    examples: Sequence[str] | None = None,
) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog=prog,
        usage=usage,
        description=description,
        epilog=build_epilog(command_groups=command_groups, examples=examples),
        formatter_class=MAILHelpFormatter,
    )


def add_hidden_subparsers(parser: argparse.ArgumentParser):
    return parser.add_subparsers(
        metavar="<command>",
        help=argparse.SUPPRESS,
    )
