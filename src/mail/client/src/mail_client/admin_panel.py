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
    cmd_login,
    cmd_ping,
    cmd_user_delete,
    cmd_user_get,
    cmd_user_list,
    cmd_user_post,
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
    user_delete_p.add_argument("worker_name", help="the name of the user to delete")
    user_delete_p.set_defaults(func=cmd_user_delete, cmd="user-delete")

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
