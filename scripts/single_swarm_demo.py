import asyncio
import logging

from mail.api import MAILSwarmTemplate
from mail.logger import init_logger

init_logger()
logger = logging.getLogger("mail")

async def main():
    swarm_template = MAILSwarmTemplate.from_swarm_json_file("swarms.json", "example-no-proxy")
    swarm = swarm_template.instantiate(instance_params={"user_token": ""})
    task_response, events = await swarm.post_message_and_run(
        subject="New Message", 
        body="what will the weather be in San Francisco tomorrow?",
        show_events=True,
    )
    print(task_response)
    print(events)

if __name__ == "__main__":
    asyncio.run(main())