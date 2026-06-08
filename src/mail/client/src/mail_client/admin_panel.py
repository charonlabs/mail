# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import argparse

from mail_client.commands import (
    cmd_agent_delete,
    cmd_agent_get,
    cmd_agent_list,
    cmd_agent_post,
    cmd_daemon_delete,
    cmd_daemon_get,
    cmd_daemon_list,
    cmd_daemon_post,
    cmd_list_delete,
    cmd_list_get_admin,
    cmd_list_list,
    cmd_list_member_delete,
    cmd_list_member_post,
    cmd_list_patch,
    cmd_list_post,
    cmd_login,
    cmd_ping,
    cmd_swarm_delete,
    cmd_swarm_post,
    cmd_user_delete,
    cmd_user_get,
    cmd_user_list,
    cmd_user_post,
    cmd_webhook_delete,
    cmd_webhook_get,
    cmd_webhook_list,
    cmd_webhook_patch,
    cmd_webhook_post,
    cmd_whoami,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mail-admin",
        usage="mail-admin [option]... <command> [argument]...",
        description="A Python CLI client admin panel for the Multi-Agent Interface Layer (MAIL)",
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
    # Agent helpers
    #
    # command `agent-list`
    agent_list_d = "get a list of agents on the MAIL server"
    agent_list_p = subparsers.add_parser(
        "agent-list",
        aliases=["al"],
        prog="mail-admin agent-list",
        help=agent_list_d,
        description=agent_list_d,
    )
    agent_list_p.set_defaults(func=cmd_agent_list, cmd="agent-list")

    # command `agent-get`
    agent_get_d = "get a specific agent by local address on the MAIL server"
    agent_get_p = subparsers.add_parser(
        "agent-get",
        aliases=["ag"],
        prog="mail-admin agent-get",
        help=agent_get_d,
        description=agent_get_d,
    )
    agent_get_p.add_argument(
        "local_address", help="the local address of the agent to get (agent@swarm)"
    )
    agent_get_p.set_defaults(func=cmd_agent_get, cmd="agent-get")

    # command `agent-post`
    agent_post_d = (
        "create a new agent on the MAIL server with the specified credentials"
    )
    agent_post_p = subparsers.add_parser(
        "agent-post",
        aliases=["ap"],
        prog="mail-admin agent-post",
        help=agent_post_d,
        description=agent_post_d,
    )
    agent_post_p.add_argument(
        "local_address", help="the local address of the agent to create (agent@swarm)"
    )
    agent_post_p.set_defaults(func=cmd_agent_post, cmd="agent-post")

    # command `agent-delete`
    agent_delete_d = "delete an existing agent by local address on the MAIL server"
    agent_delete_p = subparsers.add_parser(
        "agent-delete",
        aliases=["ad"],
        prog="mail-admin agent-delete",
        help=agent_delete_d,
        description=agent_delete_d,
    )
    agent_delete_p.add_argument(
        "local_address", help="the local address of the agent to delete (agent@swarm)"
    )
    agent_delete_p.set_defaults(func=cmd_agent_delete, cmd="agent-delete")

    #
    # Daemon helpers
    #
    # command `daemon-list`
    daemon_list_d = "get a list of daemons on the MAIL server"
    daemon_list_p = subparsers.add_parser(
        "daemon-list",
        aliases=["dl"],
        prog="mail-admin daemon-list",
        help=daemon_list_d,
        description=daemon_list_d,
    )
    daemon_list_p.set_defaults(func=cmd_daemon_list, cmd="daemon-list")

    # command `daemon-get`
    daemon_get_d = "get a specific daemon by local address on the MAIL server"
    daemon_get_p = subparsers.add_parser(
        "daemon-get",
        aliases=["dg"],
        prog="mail-admin daemon-get",
        help=daemon_get_d,
        description=daemon_get_d,
    )
    daemon_get_p.add_argument(
        "local_address", help="the local address of the daemon to get (daemon@swarm)"
    )
    daemon_get_p.set_defaults(func=cmd_daemon_get, cmd="daemon-get")

    # command `daemon-post`
    daemon_post_d = (
        "create a new daemon on the MAIL server with the specified credentials"
    )
    daemon_post_p = subparsers.add_parser(
        "daemon-post",
        aliases=["dp"],
        prog="mail-admin daemon-post",
        help=daemon_post_d,
        description=daemon_post_d,
    )
    daemon_post_p.add_argument("worker_name", help="the name to use for the new daemon")
    daemon_post_p.set_defaults(func=cmd_daemon_post, cmd="daemon-post")

    # command `daemon-delete`
    daemon_delete_d = "delete an existing daemon by worker name on the MAIL server"
    daemon_delete_p = subparsers.add_parser(
        "daemon-delete",
        aliases=["dd"],
        prog="mail-admin daemon-delete",
        help=daemon_delete_d,
        description=daemon_delete_d,
    )
    daemon_delete_p.add_argument("worker_name", help="the name of the daemon to delete")
    daemon_delete_p.set_defaults(func=cmd_daemon_delete, cmd="daemon-delete")

    #
    # User helpers
    #
    # command `user-list`
    user_list_d = "get a list of users on the MAIL server"
    user_list_p = subparsers.add_parser(
        "user-list",
        aliases=["ul"],
        prog="mail-admin user-list",
        help=user_list_d,
        description=user_list_d,
    )
    user_list_p.set_defaults(func=cmd_user_list, cmd="user-list")

    # command `user-get`
    user_get_d = "get a specific user by user ID on the MAIL server"
    user_get_p = subparsers.add_parser(
        "user-get",
        aliases=["ug"],
        prog="mail-admin user-get",
        help=user_get_d,
        description=user_get_d,
    )
    user_get_p.add_argument("user_id", help="the ID of the user to get")
    user_get_p.set_defaults(func=cmd_user_get, cmd="user-get")

    # command `user-post`
    user_post_d = "create a new user on the MAIL server with the specified credentials"
    user_post_p = subparsers.add_parser(
        "user-post",
        aliases=["up"],
        prog="mail-admin user-post",
        help=user_post_d,
        description=user_post_d,
    )
    user_post_p.add_argument("user_id", help="the ID to use for the new user")
    user_post_p.set_defaults(func=cmd_user_post, cmd="user-post")

    # command `user-delete`
    user_delete_d = "delete an existing user by user ID on the MAIL server"
    user_delete_p = subparsers.add_parser(
        "user-delete",
        aliases=["ud"],
        prog="mail-admin user-delete",
        help=user_delete_d,
        description=user_delete_d,
    )
    user_delete_p.add_argument("user_id", help="the name of the user to delete")
    user_delete_p.set_defaults(func=cmd_user_delete, cmd="user-delete")

    #
    # Swarm helpers
    #
    # command `swarm-post`
    swarm_post_d = "create a new swarm on the MAIL server with the specified info"
    swarm_post_p = subparsers.add_parser(
        "swarm-post",
        aliases=["sp"],
        prog="mail-admin swarm-post",
        help=swarm_post_d,
        description=swarm_post_d,
    )
    swarm_post_p.add_argument("name", help="the name of the swarm to create")
    swarm_post_p.add_argument(
        "description", help="the description to use for the new swarm"
    )
    swarm_post_p.add_argument(
        "-k",
        "--keywords",
        nargs="+",
        default=[],
        help="the keywords to use for this swarm (default: %(default)s)",
    )
    swarm_post_p.set_defaults(func=cmd_swarm_post, cmd="swarm-post")

    # command `swarm-delete`
    swarm_delete_d = "delete an existing swarm by name from the MAIL server"
    swarm_delete_p = subparsers.add_parser(
        "swarm-delete",
        aliases=["sd"],
        prog="mail-admin swarm-delete",
        help=swarm_delete_d,
        description=swarm_delete_d,
    )
    swarm_delete_p.add_argument(
        "swarm_name", help="the name of the swarm on the server to delete"
    )
    swarm_delete_p.set_defaults(func=cmd_swarm_delete, cmd="swarm-delete")

    #
    # Webhook helpers
    #
    # command `webhook-list`
    webhook_list_d = "list all webhooks on the MAIL server"
    webhook_list_p = subparsers.add_parser(
        "webhook-list",
        aliases=["wl"],
        prog="mail-admin webhook-list",
        help=webhook_list_d,
        description=webhook_list_d,
    )
    webhook_list_p.set_defaults(func=cmd_webhook_list, cmd="webhook-list")

    # command `webhook-get`
    webhook_get_d = "get an existing webhook by ID on the MAIL server"
    webhook_get_p = subparsers.add_parser(
        "webhook-get",
        aliases=["wg"],
        prog="mail-admin webhook-get",
        help=webhook_get_d,
        description=webhook_get_d,
    )
    webhook_get_p.add_argument("webhook_id", help="the ID of the webhook to get")
    webhook_get_p.set_defaults(func=cmd_webhook_get, cmd="webhook-get")

    # command `webhook-post`
    webhook_post_d = "create a new webhook on the MAIL server"
    webhook_post_p = subparsers.add_parser(
        "webhook-post",
        aliases=["wp"],
        prog="mail-admin webhook-post",
        help=webhook_post_d,
        description=webhook_post_d,
    )
    webhook_post_p.add_argument("url", help="the URL to hit for this webhook")
    webhook_post_p.add_argument("secret", help="the secret to use for this webhook")
    webhook_post_p.add_argument(
        "-e",
        "--events",
        nargs="+",
        default=["mail.delivered"],
        help="the event(s) for this webhook",
    )
    webhook_post_p.set_defaults(func=cmd_webhook_post, cmd="webhook-post")

    # command `webhook-patch`
    webhook_patch_d = "update an existing webhook on the MAIL server"
    webhook_patch_p = subparsers.add_parser(
        "webhook-patch",
        aliases=["wP"],
        prog="mail-admin webhook-patch",
        help=webhook_patch_d,
        description=webhook_patch_d,
    )
    webhook_patch_p.add_argument("webhook_id", help="the ID of the webhook to update")
    webhook_patch_p.add_argument("-u", "--url", help="the new URL to use, if any")
    webhook_patch_p.add_argument("-s", "--secret", help="the new secret to use, if any")
    webhook_patch_p.set_defaults(func=cmd_webhook_patch, cmd="webhook-patch")

    # command `webhook-delete`
    webhook_delete_d = "delete an existing webhook by ID on the MAIL server"
    webhook_delete_p = subparsers.add_parser(
        "webhook-delete",
        aliases=["wd"],
        prog="mail-admin webhook-delete",
        help=webhook_delete_d,
        description=webhook_delete_d,
    )
    webhook_delete_p.add_argument("webhook_id", help="the ID of the webhook to delete")
    webhook_delete_p.set_defaults(func=cmd_webhook_delete, cmd="webhook-delete")

    #
    # Mailing list helpers
    #
    # command `list-list`
    list_list_d = "get all mailing lists on the MAIL server"
    list_list_p = subparsers.add_parser(
        "list-list",
        aliases=["ll"],
        prog="mail-admin list-list",
        help=list_list_d,
        description=list_list_d,
    )
    list_list_p.set_defaults(func=cmd_list_list, cmd="list-list")

    # command `list-get`
    list_get_d = "get a specific mailing list on the MAIL server by address"
    list_get_p = subparsers.add_parser(
        "list-get",
        aliases=["lg"],
        prog="mail-admin list-get",
        help=list_get_d,
        description=list_get_d,
    )
    list_get_p.add_argument(
        "list_address", help="the address of the mailing list to get"
    )
    list_get_p.set_defaults(func=cmd_list_get_admin, cmd="list-get")

    # command `list-post`
    list_post_d = "create a new mailing list on the MAIL server"
    list_post_p = subparsers.add_parser(
        "list-post",
        aliases=["lp"],
        prog="mail-admin list-post",
        help=list_post_d,
        description=list_post_d,
    )
    list_post_p.add_argument("name", help="the name of the new mailing list")
    list_post_p.add_argument(
        "swarm_name", help="the name of the swarm to use for this mailing list"
    )
    list_post_p.add_argument("owner", help="the MAIL address of the mailing list owner")
    list_post_p.add_argument(
        "-m",
        "--members",
        nargs="+",
        default=[],
        help="the MAIL addresses of members to add to this mailing list (default: %(default)s",
    )
    list_post_p.set_defaults(func=cmd_list_post, cmd="list-post")

    # command `list-patch`
    list_patch_d = "update an existing mailing list on the MAIL server"
    list_patch_p = subparsers.add_parser(
        "list-patch",
        aliases=["lP"],
        prog="mail-admin list-patch",
        help=list_patch_d,
        description=list_patch_d,
    )
    list_patch_p.set_defaults(func=cmd_list_patch, cmd="list-patch")

    # command `list-delete`
    list_delete_d = "delete an existing mailing list on the MAIL server by address"
    list_delete_p = subparsers.add_parser(
        "list-delete",
        aliases=["ld"],
        prog="mail-admin list-delete",
        help=list_delete_d,
        description=list_delete_d,
    )
    list_delete_p.add_argument(
        "list_address", help="the address of the mailing list to delete"
    )
    list_delete_p.set_defaults(func=cmd_list_delete, cmd="list-delete")

    # command `list-member-post`
    list_member_post_d = (
        "add a new member to an existing mailing list on the MAIL server"
    )
    list_member_post_p = subparsers.add_parser(
        "list-member-post",
        aliases=["lmp"],
        prog="mail-admin list-member-post",
        help=list_member_post_d,
        description=list_member_post_d,
    )
    list_member_post_p.add_argument(
        "list_address", help="the MAIL address of the mailing list to add a member to"
    )
    list_member_post_p.add_argument(
        "member_address",
        help="the MAIL address of the member to add to this mailing list",
    )
    list_member_post_p.set_defaults(func=cmd_list_member_post, cmd="list-member-post")

    # command `list-member-delete`
    list_member_delete_d = (
        "delete a member from an existing mailing list on the MAIL server"
    )
    list_member_delete_p = subparsers.add_parser(
        "list-member-delete",
        aliases=["lmd"],
        prog="mail-admin list-member-delete",
        help=list_member_delete_d,
        description=list_member_delete_d,
    )
    list_member_delete_p.add_argument(
        "list_address",
        help="the MAIL address of the mailing list to remove a member from",
    )
    list_member_delete_p.add_argument(
        "member_address",
        help="the MAIL address of the member to remove from this mailing list",
    )
    list_member_delete_p.set_defaults(
        func=cmd_list_member_delete, cmd="list-member-delete"
    )

    # parse and handle args
    args = parser.parse_args()

    try:
        func = args.func
    except AttributeError:
        parser.print_usage()
        print("for help, run `mail-admin -h`/`mail-admin --help`")
        exit(1)

    try:
        func(args)
    except Exception as e:
        print(f"command {args.cmd} failed: {e}")
        exit(1)
