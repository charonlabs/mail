import asyncio
import json
import logging

from mail.api import MAILSwarmTemplate
from mail.utils import init_logger

init_logger()
logger = logging.getLogger("mail")


async def main():
    swarm_template = MAILSwarmTemplate.from_swarm_json_file("example-no-proxy")
    swarm = swarm_template.instantiate(instance_params={"user_token": ""})
    task_response, events = await swarm.post_message_and_run(
        "can you get the weather agent to get the weather forecast for San Francisco tomorrow and return the first result?",
        show_events=True,
    )
    print(json.dumps(task_response, indent=2))
    print(json.dumps(events, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
