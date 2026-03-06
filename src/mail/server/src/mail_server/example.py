# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uuid

from mail_protocol.core.swarm import MAILSwarm

from mail_server.api import MAILServer

server = MAILServer(
    swarm=MAILSwarm(
        name="example-mail-server",
        agents=["supervisor"],
        entrypoints=["supervisor"],
        keywords=["example"],
        description="Example MAIL server",
        metadata={},
    )
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
