# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MAIL Contributors
"""Generate the CLI reference pages under docs/references/ from the argparse
parsers that each MAIL command builds.

Each MAIL CLI exposes a ``build_parser() -> argparse.ArgumentParser``. This
script imports those parsers and renders one Markdown reference per CLI, so the
docs cannot drift from the actual flags and subcommands. Regenerate with:

    uv run python scripts/build_cli_docs.py

The generated pages are committed; do not edit them by hand.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "references"

# (output filename, page title, dotted path to build_parser, console script name)
CLIS = [
    ("client-cli.md", "Client CLI", "mail_client.cli", "mail"),
    ("admin-cli.md", "Admin CLI", "mail_client.admin_panel", "mail-admin"),
    ("server-cli.md", "Server CLI", "mail_server.cli", "mail-server"),
    ("daemon-cli.md", "Daemon CLI", "mail_daemon.cli", "mail-daemon"),
]

BANNER = (
    "> **Generated file — do not edit by hand.** Regenerate with "
    "`uv run python scripts/build_cli_docs.py` after changing the CLI. "
    "See [Regenerate API Artifacts](../howtos/regenerate-api-artifacts.md)."
)


def _metavar(action: argparse.Action) -> str:
    """A display placeholder for an option/positional that takes a value."""
    if action.nargs == 0:
        return ""
    if action.metavar:
        return str(action.metavar)
    if action.choices:
        return "{" + ",".join(str(c) for c in action.choices) + "}"
    return action.dest.upper()


def _help_text(action: argparse.Action, prog: str) -> str:
    """Expand argparse %-substitutions (e.g. %(default)s) the way --help does."""
    raw = (action.help or "").strip()
    if "%" not in raw:
        return raw
    params = {**vars(action), "prog": prog}
    if params.get("choices") is not None:
        params["choices"] = ", ".join(str(c) for c in params["choices"])
    try:
        return raw % params
    except (KeyError, ValueError, TypeError):
        return raw


def _render_option(action: argparse.Action, prog: str) -> str:
    flags = ", ".join(f"`{opt}`" for opt in action.option_strings)
    meta = _metavar(action)
    if meta:
        flags += f" `{meta}`"
    help_text = _help_text(action, prog)
    return f"- {flags} — {help_text}".rstrip(" —")


def _render_positional(action: argparse.Action, prog: str) -> str:
    name = action.metavar or action.dest
    help_text = _help_text(action, prog)
    return f"- `{name}` — {help_text}".rstrip(" —")


def _user_actions(parser: argparse.ArgumentParser):
    """Actions worth documenting: skip -h/--help and the subparsers action."""
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        yield action


def _subparsers_action(parser: argparse.ArgumentParser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _arg_items(parser: argparse.ArgumentParser) -> tuple[list[str], list[str]]:
    prog = parser.prog
    positionals = [
        _render_positional(a, prog)
        for a in _user_actions(parser)
        if not a.option_strings
    ]
    options = [
        _render_option(a, prog) for a in _user_actions(parser) if a.option_strings
    ]
    return positionals, options


def _labeled_block(parser: argparse.ArgumentParser) -> list[str]:
    """Argument/option lists under a bold mini-label (used inside subcommands)."""
    positionals, options = _arg_items(parser)
    lines: list[str] = []
    if positionals:
        lines += ["**Arguments:**", "", *positionals, ""]
    if options:
        lines += ["**Options:**", "", *options, ""]
    return lines


def _render_subcommands(sub_action: argparse._SubParsersAction) -> list[str]:
    # Map each subparser object to all the names (primary + aliases) that reach it.
    names_by_parser: dict[int, list[str]] = {}
    for name, subparser in sub_action.choices.items():
        names_by_parser.setdefault(id(subparser), []).append(name)

    lines: list[str] = ["## Commands", ""]
    for pseudo in sub_action._choices_actions:
        primary = pseudo.dest
        subparser = sub_action.choices[primary]
        aliases = [n for n in names_by_parser[id(subparser)] if n != primary]
        heading = f"### `{primary}`"
        if aliases:
            heading += "  (aliases: " + ", ".join(f"`{a}`" for a in aliases) + ")"
        lines.append(heading)
        lines.append("")
        summary = (pseudo.help or subparser.description or "").strip()
        if summary:
            lines.append(summary)
            lines.append("")
        lines.extend(_labeled_block(subparser))
    return lines


def render_page(title: str, module_path: str, script: str) -> str:
    module = importlib.import_module(module_path)
    parser: argparse.ArgumentParser = module.build_parser()

    lines = [f"# {title}", "", "Status: generated", "", BANNER, ""]
    description = (parser.description or "").strip()
    if description:
        lines.append(description)
        lines.append("")
    lines.append(f"Invoke as `{script}` (or `uv run {script}` from a workspace "
                 f"checkout). Source: `{module_path.replace('.', '/')}.py`.")
    lines.append("")

    sub_action = _subparsers_action(parser)
    positionals, options = _arg_items(parser)
    if positionals:
        lines += ["## Arguments", "", *positionals, ""]
    if options:
        lines += ["## Global options" if sub_action else "## Options", "", *options, ""]

    if sub_action is not None:
        lines.extend(_render_subcommands(sub_action))

    text = "\n".join(lines).rstrip() + "\n"
    return text


def main() -> None:
    for filename, title, module_path, script in CLIS:
        page = render_page(title, module_path, script)
        out = DOCS_DIR / filename
        out.write_text(page, encoding="utf-8")
        print(f"wrote {out.relative_to(DOCS_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
