# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio

from mail import MAILSwarmTemplate
from mail.utils.logger import init_logger


async def main():
    init_logger()
    template = MAILSwarmTemplate.from_swarm_json_file("example-no-proxy", "swarms.json")
    swarm = template.instantiate(
        {
            "user_token": "admin_8",
        }
    )
    result = await swarm.post_message_and_run(
        "what will the weather in San Francisco be tomorrow? ask the `weather` agent to obtain a forecast and return it to you. from there, synthesize a summary for me and call `task_complete`. thanks!",
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
