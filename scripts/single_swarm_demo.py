# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import json

from mail import MAILSwarmTemplate
from mail.utils.logger import init_logger


async def main():
    init_logger()
    template = MAILSwarmTemplate.from_swarm_json_file("example-no-proxy", "swarms.json")
    swarm = template.instantiate(
        {
            "user_token": "dummy",
        }
    )
    result = await swarm.post_message_and_run(
        "what will the weather in San Francisco be tomorrow? ask the `weather` agent to obtain a forecast and return it to you. from there, synthesize a summary for me and call `task_complete`. thanks!",
    )
    print(f"result: {json.dumps(result[0], indent=2)}")
    print(f"events: {json.dumps(result[1], indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
