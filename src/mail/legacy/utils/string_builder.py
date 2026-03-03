# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from pathlib import Path

from mail.core.tools import get_tool_help

SPEC_PATH = Path(__file__).resolve().parents[3] / "spec" / "SPEC.md"


def build_mail_help_string(
    name: str,
    swarm: str,
    get_summary: bool = True,
    get_identity: bool = False,
    get_tool_help: list[str] | None = None,
    get_full_protocol: bool = False,
) -> str:
    """
    Build the string used by the MAIL `help` tool.
    """
    string = ""
    if get_summary:
        string += _get_summary()
    if get_identity:
        string += _get_identity(name, swarm)
    if get_tool_help:
        string += _get_tool_help(get_tool_help)
    if get_full_protocol:
        string += _get_full_protocol()

    return string.strip()


def _get_summary() -> str:
    """
    Get a summary of MAIL.
    This is included in the `help` tool's output by default.
    """
    return _create_section("summary", SUMMARY_STRING)


def _get_identity(name: str, swarm: str) -> str:
    """
    Get the identity of the agent.
    """
    return _create_section(
        "your identity", IDENTITY_STRING.format(name=name, swarm=swarm)
    )


def _get_tool_help(tool_help: list[str] | None = None) -> str:
    """
    Get the help for the given tools.
    """
    tool_help = tool_help or []
    return _create_section("tool help", f"\n{get_tool_help(tool_help)}")


def _get_full_protocol() -> str:
    """
    Get the full MAIL protocol specification.
    """
    if SPEC_PATH.is_file():
        content = SPEC_PATH.read_text(encoding="utf-8")
    else:
        content = "The MAIL protocol specification could not be located on disk."
    return _create_section("full MAIL protocol specification", content)


def _create_section(title: str, content: str, capitalize: bool = True) -> str:
    """
    Create a section of the `help` tool's output in a pseudo-Markdown format.
    """
    return f"===== {title.upper() if capitalize else title} =====\n\n{content}\n\n"


SUMMARY_STRING = """
You are an agent that is part of a swarm following the MAIL (Multi-Agent Interface Layer) protocol.
MAIL defines a set of tools that allow you to communicate with other agents in an email-like syntax.
You may be given 'actions' (third-party tools) that you can use to perform tasks that are outside the scope of MAIL.
These tool calls are processed by an asynchronous message queue in the runtime that operates until a user-specified task is complete.

# MAIL Tools
MAIL defines a suite of core tools that mirror the functionality of email.
Examples include `send_request`, `send_broadcast`, and `await_message`.
These tool calls are processed by the runtime and their functions are executed.
Note that the tool call responses for message-sending calls (`send_request`, `send_response`, `send_interrupt`, `send_broadcast`) are indicators of whether or not the operation was successful.
A message response is NOT part of the tool call response--if one exists, it will be served to you in a subsequent prompt. 

# Actions
You may have access to actions, which are third-party tools that you can use to perform tasks that are outside the scope of MAIL.
These actions are functionally identical to MAIL tools and are called in the same way.
Examples of possible actions include `web_search`, `code_interpreter`, and `file_manager`.
The result of an action call will be part of the tool call response; you will be reprompted by the runtime with an '::action_complete_broadcast::'.

# User Tasks
A MAIL swarm works by having a user specify a task for the swarm to complete.
Said task is defined by a message from the user to an entrypoint agent in the swarm.
The swarm will then run until `task_complete` is called by an agent capable of doing so.
Note that a user may resume a task after it has been completed--this enables multi-turn conversations between the user and the swarm.
Resumed tasks operate the same way as new tasks; they will run until `task_complete` is called.

# Tips
- To view your identity (agent name, swarm, etc.), call the `help` tool with `get_identity=True`.
- To view the full MAIL protocol specification, call the `help` tool with `get_full_protocol=True`.

# Notes
This summary message is included in the `help` tool's output by default.
You can disable it by calling the `help` tool with `get_summary=False`.
"""


IDENTITY_STRING = """
**Name**: {name}
**Swarm**: {swarm}
**Local Address**: {name} (same as name)
**Interswarm Address**: {name}@{swarm}
"""
