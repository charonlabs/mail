# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import argparse

from mail_client.commands import (
    cmd_compose,
    cmd_drafts,
    cmd_drafts_open,
    cmd_inbox,
    cmd_inbox_open,
    cmd_login,
    cmd_outbox,
    cmd_outbox_open,
    cmd_ping,
    cmd_send,
    cmd_swarm_get,
    cmd_swarm_list,
    cmd_trash,
    cmd_trash_open,
    cmd_whoami,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mail",
        usage="mail [option...] <command> [argument...]",
        description="The Python CLI client for the Multi-Agent Interface Layer (MAIL)",
        epilog="Copyright (c) 2026 Addison Kline",
    )
    parser.add_argument(
        "-o",
        "--output",
        choices=["text", "json"],
        default="text",
        help="the output style for this CLI command (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(title="commands")

    #
    # Utility commands
    #
    # command `ping`
    ping_d = "ping a MAIL server"
    ping_p = subparsers.add_parser(
        "ping",
        aliases=["p"],
        prog="mail ping",
        help=ping_d,
        description=ping_d,
    )
    ping_p.set_defaults(func=cmd_ping, cmd="ping")

    # command `login`
    login_d = "log into a MAIL server"
    login_p = subparsers.add_parser(
        "login", aliases=["l"], prog="mail login", help=login_d, description=login_d
    )
    login_p.set_defaults(func=cmd_login, cmd="login")

    # command `whoami`
    whoami_d = "get authenticated user-agent info from a MAIL server"
    whoami_p = subparsers.add_parser(
        "whoami",
        aliases=["me", "id"],
        prog="mail whoami",
        help=whoami_d,
        description=whoami_d,
    )
    whoami_p.set_defaults(func=cmd_whoami, cmd="whoami")

    #
    # Core MAIL operations
    #
    # command `compose`
    compose_d = "draft a new MAIL message prior to sending"
    compose_p = subparsers.add_parser(
        "compose",
        aliases=["c"],
        prog="mail compose",
        help=compose_d,
        description=compose_d,
    )
    compose_p.add_argument("subject", help="the subject line of the message to draft")
    compose_p.add_argument("body", help="the body of the message to draft")
    compose_p.set_defaults(func=cmd_compose, cmd="compose")

    # command `send`
    send_d = "send a drafted MAIL message to the specified address(es)"
    send_p = subparsers.add_parser(
        "send",
        aliases=["s"],
        prog="mail send",
        help=send_d,
        description=send_d,
    )
    send_p.add_argument("draft_id", help="the ID of the existing draft to send")
    send_p.add_argument(
        "to", nargs="+", help="the address(es) to deliver this message to"
    )
    send_p.set_defaults(func=cmd_send, cmd="send")

    # command `inbox`
    inbox_d = "open your MAIL inbox"
    inbox_p = subparsers.add_parser(
        "inbox", aliases=["i"], prog="mail inbox", help=inbox_d, description=inbox_d
    )
    inbox_p.set_defaults(func=cmd_inbox, cmd="inbox")

    # command `inbox-open`
    inbox_open_d = "open a specific message by ID in your MAIL inbox"
    inbox_open_p = subparsers.add_parser(
        "inbox-open",
        aliases=["open", "o"],
        prog="mail inbox-open",
        help=inbox_open_d,
        description=inbox_open_d,
    )
    inbox_open_p.add_argument("message_id", help="the ID of the message to open")
    inbox_open_p.set_defaults(func=cmd_inbox_open, cmd="inbox-open")

    # command `outbox`
    outbox_d = "open your MAIL outbox"
    outbox_p = subparsers.add_parser(
        "outbox", aliases=["O"], prog="mail outbox", help=outbox_d, description=outbox_d
    )
    outbox_p.set_defaults(func=cmd_outbox, cmd="outbox")

    # command `outbox-open`
    outbox_open_d = "open a specific message by ID in your MAIL outbox"
    outbox_open_p = subparsers.add_parser(
        "outbox-open",
        aliases=["Oopen", "Oo"],
        prog="mail outbox-open",
        help=outbox_open_d,
        description=outbox_open_d,
    )
    outbox_open_p.add_argument("message_id", help="the ID of the message to open")
    outbox_open_p.set_defaults(func=cmd_outbox_open, cmd="outbox-open")

    # command `drafts`
    drafts_d = "list your existing message drafts"
    drafts_p = subparsers.add_parser(
        "drafts",
        aliases=["d"],
        prog="mail drafts",
        help=drafts_d,
        description=drafts_d,
    )
    drafts_p.set_defaults(func=cmd_drafts, cmd="drafts")

    # command `drafts-open`
    drafts_open_d = "open a specific existing draft by ID"
    drafts_open_p = subparsers.add_parser(
        "drafts-open",
        aliases=["do"],
        prog="mail drafts-open",
        help=drafts_open_d,
        description=drafts_open_d,
    )
    drafts_open_p.add_argument("draft_id", help="the ID of the drafted message to open")
    drafts_open_p.set_defaults(func=cmd_drafts_open, cmd="drafts-open")

    # command `trash`
    trash_d = "list your existing trashed messages"
    trash_p = subparsers.add_parser(
        "trash", aliases=["t"], prog="mail trash", help=trash_d, description=trash_d
    )
    trash_p.set_defaults(func=cmd_trash, cmd="trash")

    # command `trash-open`
    trash_open_d = "open a specific message in trash by ID"
    trash_open_p = subparsers.add_parser(
        "trash-open",
        aliases=["to"],
        prog="mail trash-open",
        help=trash_open_d,
        description=trash_open_d,
    )
    trash_open_p.add_argument(
        "message_id", help="the ID of the message in trash to open"
    )
    trash_open_p.set_defaults(func=cmd_trash_open, cmd="trash-open")

    #
    # Swarm helpers
    #
    # command `swarm-list`
    swarm_list_d = "get the swarms on this MAIL server"
    swarm_list_p = subparsers.add_parser(
        "swarm-list",
        aliases=["swarms", "sl"],
        prog="mail swarm-list",
        help=swarm_list_d,
        description=swarm_list_d,
    )
    swarm_list_p.set_defaults(func=cmd_swarm_list, cmd="swarm-list")

    # command `swarm-get`
    swarm_get_d = "get a specific swarm by name on this MAIL server"
    swarm_get_p = subparsers.add_parser(
        "swarm-get",
        aliases=["swarm", "sg"],
        prog="mail swarm-get",
        help=swarm_get_d,
        description=swarm_get_d,
    )
    swarm_get_p.add_argument("swarm_name", help="the name of the MAIL swarm to get")
    swarm_get_p.set_defaults(func=cmd_swarm_get, cmd="swarm-get")

    # parse and handle args
    args = parser.parse_args()

    try:
        func = args.func
    except AttributeError:
        parser.print_usage()
        print("for help, run `mail -h`/`mail --help`")
        exit(1)

    try:
        func(args)
    except Exception as e:
        print(f"command {args.cmd} failed: {e}")
        exit(1)
