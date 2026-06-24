# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import argparse
import asyncio

from mail_protocol.cli_help import add_license_argument
from mail_protocol.core.validators import (
    validate_agent_names,
    validate_daemon_worker_names,
    validate_host,
    validate_swarm_description,
    validate_swarm_keywords,
    validate_swarm_name,
    validate_user_names,
)

from mail_server.backends.memory.init import init_memory_backend


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="backend-init",
        usage="backend-init [option]...",
        description="Initialize the MAIL server backend for use by mail-server",
        epilog="Copyright (c) 2025-present MAIL Contributors",
    )
    add_license_argument(parser)
    parser.add_argument(
        "-t",
        "--type",
        default="memory",
        choices=["memory", "sqlite"],
        help="the type of backend to initialize (default: %(default)s)",
    )
    parser.add_argument(
        "-d",
        "--deployment",
        default="default",
        help="the MAIL server deployment to create (default: %(default)s)",
    )
    parser.add_argument(
        "-s",
        "--swarm",
        default="default",
        help="the name of the primary MAIL swarm for the server to use (default: %(default)s)",
    )
    parser.add_argument(
        "-sd",
        "--swarm-description",
        default="A MAIL swarm",
        help="the description to use for this swarm (default: %(default)s)",
    )
    parser.add_argument(
        "-sk",
        "--swarm-keywords",
        nargs="+",
        default=[],
        help="the keywords to use for this swarm (default: %(default)s)",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["supervisor"],
        help="the agent(s) to register on this server (default: %(default)s)",
    )
    parser.add_argument(
        "--daemons",
        nargs="+",
        default=["dummy"],
        help="the daemon(s) to register on this server (default: %(default)s)",
    )
    parser.add_argument(
        "--users",
        nargs="+",
        default=["dummy"],
        help="the user(s) to register on this server (default: %(default)s)",
    )
    parser.add_argument(
        "--admins",
        nargs="+",
        default=["dummy"],
        help="the admin(s) to register on this server (default: %(default)s)",
    )
    parser.add_argument(
        "-H",
        "--host",
        default="example.com",
        help="the host domain or IP address to use (default: %(default)s)",
    )
    parser.add_argument(
        "--import-fs",
        action="store_true",
        help=(
            "for --type sqlite: import the existing filesystem (memory) "
            "deployment of the same name into the new SQLite database instead "
            "of seeding a fresh cast"
        ),
    )

    # parse and handle args
    args = parser.parse_args()
    be_type = args.type
    import_fs = args.import_fs
    deployment = args.deployment
    swarm = args.swarm
    swarm_description = args.swarm_description
    swarm_keywords = args.swarm_keywords
    agents = args.agents
    daemons = args.daemons
    users = args.users
    admins = args.admins
    host = args.host

    # validate args
    try:
        validate_swarm_name(swarm)
    except ValueError as e:
        print(f"invalid swarm name {swarm}: {e}")
        exit(1)
    try:
        validate_swarm_description(swarm_description)
    except ValueError as e:
        print(f"invalid swarm description {swarm_description}: {e}")
        exit(1)
    try:
        validate_swarm_keywords(swarm_keywords)
    except ValueError as e:
        print(f"invalid swarm keywords {swarm_keywords}: {e}")
        exit(1)
    try:
        validate_agent_names(agents)
    except ValueError as e:
        print(f"invalid agent names {agents}: {e}")
        exit(1)
    try:
        validate_daemon_worker_names(daemons)
    except ValueError as e:
        print(f"invalid daemon names {daemons}: {e}")
        exit(1)
    try:
        validate_user_names(users)
    except ValueError as e:
        print(f"invalid user names {users}: {e}")
        exit(1)
    try:
        validate_user_names(admins)
    except ValueError as e:
        print(f"invalid admin names {admins}: {e}")
        exit(1)
    try:
        validate_host(host)
    except ValueError as e:
        print(f"invalid host {host}: {e}")
        exit(1)
    if import_fs and be_type != "sqlite":
        print("--import-fs is only valid with --type sqlite")
        exit(1)

    # initialize backend
    match be_type:
        case "memory":
            init_memory_backend(
                deployment=deployment,
                swarm=swarm,
                swarm_description=swarm_description,
                swarm_keywords=swarm_keywords,
                agents=agents,
                daemons=daemons,
                users=users,
                admins=admins,
                host=host,
            )
        case "sqlite":
            # Imported lazily so SQLAlchemy stays off the import path for
            # memory-only initialization.
            if import_fs:
                from mail_server.backends.sqlite.migrate import (
                    import_memory_deployment,
                )

                counts = asyncio.run(
                    import_memory_deployment(deployment=deployment)
                )
                print(f"imported filesystem deployment {deployment}: {counts}")
            else:
                from mail_server.backends.sqlite.init import init_sqlite_backend

                asyncio.run(
                    init_sqlite_backend(
                        deployment=deployment,
                        swarm=swarm,
                        swarm_description=swarm_description,
                        swarm_keywords=swarm_keywords,
                        agents=agents,
                        daemons=daemons,
                        users=users,
                        admins=admins,
                        host=host,
                    )
                )
        case _:
            raise ValueError(f"invalid backend type: {be_type}")
