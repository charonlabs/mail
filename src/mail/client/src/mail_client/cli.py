# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import argparse
import contextlib
import io
from collections.abc import Callable

from mail_protocol.cli_help import add_hidden_subparsers, make_arg_parser

from mail_client.commands import (
    cmd_compose,
    cmd_drafts,
    cmd_drafts_open,
    cmd_forward,
    cmd_inbox,
    cmd_inbox_open,
    cmd_list_get,
    cmd_list_subscribe,
    cmd_list_unsubscribe,
    cmd_lists,
    cmd_login,
    cmd_outbox,
    cmd_outbox_open,
    cmd_ping,
    cmd_reply,
    cmd_send,
    cmd_swarm_get,
    cmd_swarm_list,
    cmd_trash,
    cmd_trash_open,
    cmd_whoami,
)

MARKDOWN_FIELD_LABELS = {
    "Address",
    "Agents",
    "Body",
    "Created At",
    "Delivered At",
    "Delivered By",
    "Description",
    "Draft ID",
    "Join Policy",
    "Keywords",
    "List ID",
    "Members",
    "Message ID",
    "Name",
    "Owner",
    "Received At",
    "Recipient(s)",
    "Send Policy",
    "Sender",
    "Sent At",
    "Sent By",
    "Subject",
    "Trashed At",
    "Type",
    "Updated At",
    "Visibility",
}

COMMAND_GROUPS = [
    (
        "Utility",
        [
            ("ping (p)", "Ping a MAIL server."),
            ("login (l)", "Log into a MAIL server."),
            ("whoami (me, id)", "Show authenticated user-agent info."),
        ],
    ),
    (
        "Messaging",
        [
            ("compose (c)", "Draft a new MAIL message."),
            ("send (s)", "Send a drafted message."),
            ("reply (r)", "Reply to an inbox message by ID."),
            ("forward (f)", "Forward an inbox message to new recipient(s)."),
            ("inbox (i)", "List your inbox messages."),
            ("inbox-open (open, o)", "Open an inbox message by ID."),
            ("outbox (O)", "List your sent messages."),
            ("outbox-open (Oopen, Oo)", "Open an outbox message by ID."),
            ("drafts (d)", "List message drafts."),
            ("drafts-open (do)", "Open a draft by ID."),
            ("trash (t)", "List trashed messages."),
            ("trash-open (to)", "Open a trashed message by ID."),
        ],
    ),
    (
        "Swarms",
        [
            ("swarm-list (swarms, sl)", "List swarms on the server."),
            ("swarm-get (swarm, sg)", "Get a swarm by name."),
        ],
    ),
    (
        "Mailing Lists",
        [
            ("lists", "List mailing lists."),
            ("list-get (list, lg)", "Get a list by address."),
            ("list-subscribe (ls)", "Subscribe to a list."),
            ("list-unsubscribe (lu)", "Unsubscribe from a list."),
        ],
    ),
]

EXAMPLES = [
    "mail login",
    'mail compose "Status update" "The migration is complete."',
    "mail send <draft-id> user@example",
    "mail inbox-open <message-id>",
    'mail reply <message-id> "Thanks, acknowledged."',
    "mail forward <message-id> sage@chorus@localhost",
]


def _add_tags_arg(parser: argparse.ArgumentParser) -> None:
    """
    Register the shared ``--tags`` flag for message-creating commands
    (compose, send, reply, forward). Tags are slug strings used to categorize a
    message; the default is an empty list (no tags).
    """

    parser.add_argument(
        "--tags",
        nargs="*",
        default=[],
        metavar="TAG",
        help="slug string tag(s) to attach to the message",
    )


def _add_box_filter_args(box_parser: argparse.ArgumentParser) -> None:
    """
    Register the shared query-param flags for the "GET box" commands
    (inbox, outbox, drafts, trash). Defaults are left as ``None`` so unset
    flags are simply not sent and the server applies its own defaults.
    """

    box_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max number of entries to return (1-100)",
    )
    box_parser.add_argument(
        "--offset", type=int, default=None, help="number of entries to skip"
    )
    box_parser.add_argument(
        "--sort-by",
        dest="sort_by",
        choices=["sent_at", "entered_at"],
        default=None,
        help="timestamp field to sort by",
    )
    box_parser.add_argument(
        "--order",
        choices=["asc", "desc"],
        default=None,
        help="sort direction",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = make_arg_parser(
        prog="mail",
        usage="mail [option...] <command> [argument...]",
        description="The Python CLI client for the Multi-Agent Interface Layer (MAIL)",
        command_groups=COMMAND_GROUPS,
        examples=EXAMPLES,
    )
    parser.add_argument(
        "-o",
        "--output",
        choices=["text", "json", "markdown"],
        default="text",
        help="the output style for this CLI command (default: %(default)s)",
    )
    subparsers = add_hidden_subparsers(parser)

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
    _add_tags_arg(compose_p)
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
    _add_tags_arg(send_p)
    send_p.set_defaults(func=cmd_send, cmd="send")

    # command `reply`
    reply_d = "reply to an existing inbox message"
    reply_p = subparsers.add_parser(
        "reply",
        aliases=["r"],
        prog="mail reply",
        help=reply_d,
        description=reply_d,
    )
    reply_p.add_argument("message_id", help="the ID of the inbox message to reply to")
    reply_p.add_argument("body", help="the body of the reply")
    reply_p.add_argument(
        "--subject",
        default=None,
        help="the subject of the reply (default: 'Re: <original subject>')",
    )
    _add_tags_arg(reply_p)
    reply_p.set_defaults(func=cmd_reply, cmd="reply")

    # command `forward`
    forward_d = "forward an existing inbox message to new recipient(s)"
    forward_p = subparsers.add_parser(
        "forward",
        aliases=["f"],
        prog="mail forward",
        help=forward_d,
        description=forward_d,
    )
    forward_p.add_argument(
        "message_id", help="the ID of the inbox message to forward"
    )
    forward_p.add_argument(
        "to", nargs="+", help="the address(es) to forward this message to"
    )
    forward_p.add_argument(
        "--note",
        default=None,
        help="an optional note to prepend above the forwarded message",
    )
    forward_p.add_argument(
        "--subject",
        default=None,
        help="the subject of the forward (default: 'Fwd: <original subject>')",
    )
    _add_tags_arg(forward_p)
    forward_p.set_defaults(func=cmd_forward, cmd="forward")

    # command `inbox`
    inbox_d = "open your MAIL inbox"
    inbox_p = subparsers.add_parser(
        "inbox", aliases=["i"], prog="mail inbox", help=inbox_d, description=inbox_d
    )
    _add_box_filter_args(inbox_p)
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
    _add_box_filter_args(outbox_p)
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
    _add_box_filter_args(drafts_p)
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
    _add_box_filter_args(trash_p)
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

    #
    # Mailing list helpers
    #
    # command `lists`
    lists_d = "get mailing lists on this MAIL server"
    lists_p = subparsers.add_parser(
        "lists",
        prog="mail lists",
        help=lists_d,
        description=lists_d,
    )
    lists_p.set_defaults(func=cmd_lists, cmd="lists")

    # command `list-get`
    list_get_d = "get a specific list on this MAIL server by address"
    list_get_p = subparsers.add_parser(
        "list-get",
        aliases=["list", "lg"],
        prog="mail list-get",
        help=list_get_d,
        description=list_get_d,
    )
    list_get_p.add_argument(
        "list_address", help="the address of the mailing list to get"
    )
    list_get_p.set_defaults(func=cmd_list_get, cmd="list-get")

    # command `list-subscribe`
    list_subscribe_d = "subscribe to a mailing list on this server by address"
    list_subscribe_p = subparsers.add_parser(
        "list-subscribe",
        aliases=["ls"],
        prog="mail list-subscribe",
        help=list_subscribe_d,
        description=list_subscribe_d,
    )
    list_subscribe_p.add_argument(
        "list_address", help="the address of the mailing list to subscribe to"
    )
    list_subscribe_p.set_defaults(func=cmd_list_subscribe, cmd="list-subscribe")

    # command `list-unsubscribe`
    list_unsubscribe_d = "unsubscribe from a mailing list on this server by address"
    list_unsubscribe_p = subparsers.add_parser(
        "list-unsubscribe",
        aliases=["lu"],
        prog="mail list-unsubscribe",
        help=list_unsubscribe_d,
        description=list_unsubscribe_d,
    )
    list_unsubscribe_p.add_argument(
        "list_address", help="the address of the mailing list to unsubscribe from"
    )
    list_unsubscribe_p.set_defaults(func=cmd_list_unsubscribe, cmd="list-unsubscribe")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        func = args.func
    except AttributeError:
        parser.print_usage()
        print("for help, run `mail -h`/`mail --help`")
        exit(1)

    try:
        _run_command(func, args)
    except Exception as e:
        print(f"command {args.cmd} failed: {e}")
        exit(1)


def _run_command(
    func: Callable[[argparse.Namespace], None], args: argparse.Namespace
) -> None:
    if args.output != "markdown":
        func(args)
        return

    args.output = "text"
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        func(args)

    print(_text_to_markdown(stdout.getvalue()), end="")


def _text_to_markdown(text: str) -> str:
    lines = text.splitlines()
    markdown_lines: list[str] = []
    seen_heading = False
    in_section = False
    in_body = False

    for line in lines:
        if line.startswith("=== ") and line.endswith(" ==="):
            if in_body:
                markdown_lines.append("```")
                markdown_lines.append("")
                in_body = False

            title = line.removeprefix("=== ").removesuffix(" ===")
            heading_prefix = "##" if seen_heading else "#"
            markdown_lines.append(f"{heading_prefix} {title}")
            seen_heading = True
            in_section = True
            continue

        if in_body:
            markdown_lines.append(line)
            continue

        if not line:
            markdown_lines.append("")
            continue

        label, separator, value = line.partition(":")
        if separator and label in MARKDOWN_FIELD_LABELS:
            if label == "Body":
                markdown_lines.append("- **Body:**")
                markdown_lines.append("")
                markdown_lines.append("```")
                if value.lstrip():
                    markdown_lines.append(value.lstrip())
                in_body = True
                continue

            markdown_lines.append(f"- **{label}:** {value.lstrip()}")
            continue

        if line.startswith("- "):
            markdown_lines.append(line)
            continue

        if in_section:
            markdown_lines.append(f"- {line}")
        else:
            markdown_lines.append(line)

    if in_body:
        markdown_lines.append("```")

    if not markdown_lines:
        return ""

    return "\n".join(markdown_lines) + "\n"
