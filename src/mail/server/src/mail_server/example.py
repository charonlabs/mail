# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uuid

from mail_protocol.core.swarm import MAILSwarm

from mail_server.api import MAILServer
from mail_server.auth import JWTSettings, StaticAPIKeyAuthBackend, TokenInfo

auth_backend = StaticAPIKeyAuthBackend(
    {
        "admin-key": TokenInfo(role="admin", id="admin-1"),
        "user-key": TokenInfo(role="user", id="user-1"),
        "swarm-key": TokenInfo(role="swarm", id="remote-swarm"),
    }
)

auth_settings = JWTSettings(
    secret="change-me",
    algorithm="HS256",
    lifetime_minutes=60,
)


server = MAILServer(
    swarm=MAILSwarm(
        name="example-mail-server",
        agents=["supervisor"],
        entrypoints=["supervisor"],
        keywords=["example"],
        description="Example MAIL server",
        metadata={},
    ),
    auth_backend=auth_backend,
    auth_settings=auth_settings,
)


@server.on_startup
async def on_startup(mail_server: MAILServer) -> None:
    mail_server.app.state.example_task_id = str(uuid.uuid4())


@server.on_shutdown
async def on_shutdown() -> None:
    return None


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
