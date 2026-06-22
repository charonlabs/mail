# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from __future__ import annotations

import argparse
from collections.abc import Sequence

CommandHelp = tuple[str, str]
CommandGroup = tuple[str, Sequence[CommandHelp]]

LICENSE_NOTICE = """\
MAIL - Multi-Agent Interface Layer
Copyright (c) 2025-present MAIL Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this software except in compliance with the License.
You may obtain a copy of the License at:

    http://www.apache.org/licenses/LICENSE-2.0

Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied. See the LICENSE and NOTICE files
distributed with this project for the full terms."""


class _LicenseAction(argparse.Action):
    """Print MAIL's license notice and exit, mirroring argparse's --version."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        help: str = "show license information and exit",
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        parser.exit(message=LICENSE_NOTICE + "\n")


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
    footer: str | None = "Copyright (c) 2025-present MAIL Contributors",
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


def add_license_argument(parser: argparse.ArgumentParser) -> None:
    """Add a `--license` flag that prints MAIL's license notice and exits."""
    parser.add_argument("--license", action=_LicenseAction)


def make_arg_parser(
    *,
    prog: str,
    usage: str,
    description: str,
    command_groups: Sequence[CommandGroup] | None = None,
    examples: Sequence[str] | None = None,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        usage=usage,
        description=description,
        epilog=build_epilog(command_groups=command_groups, examples=examples),
        formatter_class=MAILHelpFormatter,
    )
    add_license_argument(parser)
    return parser


def add_hidden_subparsers(parser: argparse.ArgumentParser):
    return parser.add_subparsers(
        metavar="<command>",
        help=argparse.SUPPRESS,
    )
