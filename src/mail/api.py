import datetime
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal

from sse_starlette import EventSourceResponse, ServerSentEvent

from mail.core import MAIL
from mail.factories.action import ActionFunction
from mail.factories.base import AgentFunction
from mail.message import MAILMessage, MAILRequest, create_agent_address
from mail.swarms.utils import read_python_string


class MAILAgent:
    """
    Agent class exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        factory: str,
        comm_targets: list[str],
        agent_params: dict[str, Any],
    ) -> None:
        self.name = name
        self.factory = factory
        self.comm_targets = comm_targets
        self.agent_params = agent_params
        self.agent_function = self._build_agent_function(factory, agent_params)

    def _build_agent_function(
        self,
        factory: str,
        params: dict[str, Any],
    ) -> AgentFunction:
        return read_python_string(factory)(**params)

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILAgent":
        """
        Create a MAILAgent from a JSON dump following the `swarms.json` format.
        """
        REQUIRED_FIELDS = {
            "name": str,
            "factory": str,
            "comm_targets": list[str],
            "agent_params": dict[str, Any],
        }

        data = json.loads(json_dump)

        if data is None:
            raise ValueError("agent JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"agent JSON dump missing required field: '{field}'")

        name = data["name"]
        factory = data["factory"]
        comm_targets = data["comm_targets"]
        agent_params = data["agent_params"]

        for field in REQUIRED_FIELDS:
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(
                    f"agent JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'"
                )

        return MAILAgent(
            name=name,
            factory=factory,
            comm_targets=comm_targets,
            agent_params=agent_params,
        )


class MAILAction:
    """
    Action class exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        function: str,
    ) -> None:
        self.name = name
        pass


class MAILSwarm:
    """
    Swarm class exposed via the MAIL API.
    """

    def __init__(
        self,
        swarm_name: str,
        agents: list[MAILAgent],
        actions: list[MAILAction],
        entrypoint: str,
        user_id: str = "default_user",
    ) -> None:
        self.swarm_name = swarm_name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.user_id = user_id
        self._runtime = MAIL(
            agents={agent.name: agent.agent_function for agent in agents},
            actions={action.name: action.action_function for action in actions},
            user_id=user_id,
            swarm_name=swarm_name,
            entrypoint=entrypoint,
        )

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILSwarm":
        """
        Create a MAILSwarm from a JSON dump following the `swarms.json` format.
        """
        REQUIRED_FIELDS = {
            "name": str,
            "agents": list[dict[str, Any]],
            "actions": list[dict[str, Any]],
            "entrypoint": str,
        }

        data = json.loads(json_dump)

        if data is None:
            raise ValueError("swarm JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"swarm JSON dump missing required field: '{field}'")

        name = data["name"]
        agents = data["agents"]
        actions = data["actions"]
        entrypoint = data["entrypoint"]

        for field in REQUIRED_FIELDS:
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(
                    f"swarm JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'"
                )

        return MAILSwarm(
            swarm_name=name,
            agents=agents,
            actions=actions,
            entrypoint=entrypoint,
            user_id=data.get("user_id", "default_user"),
        )

    @staticmethod
    def from_swarm_json_file(json_filepath: str, swarm_name: str) -> "MAILSwarm":
        """
        Create a MAILSwarm from a JSON file following the `swarms.json` format.
        """
        with open(json_filepath, "r") as f:
            contents = f.read()
            full_json = json.loads(contents)
            for swarm in full_json:
                if swarm["name"] == swarm_name:
                    return MAILSwarm.from_swarm_json(json.dumps(swarm))
                raise ValueError(f"swarm '{swarm_name}' not found in {json_filepath}")

        raise ValueError(f"trouble reading filepath: '{json_filepath}'")

    async def post_message(
        self,
        subject: str,
        body: str,
        entrypoint: str | None = None,
        show_events: bool = False,
        timeout: float = 3600.0,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Post a message to the swarm and return the task completion response.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self._build_message(subject, body, [entrypoint], "request")
        response = await self._runtime.submit_and_wait(message, timeout)

        if show_events:
            return response, self._runtime.get_events_by_task_id(
                message["message"]["task_id"]
            )
        else:
            return response, []

    async def post_message_stream(
        self,
        subject: str,
        body: str,
        entrypoint: str | None = None,
        timeout: float = 3600.0,
    ) -> EventSourceResponse:
        """
        Post a message to the swarm and stream the response.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self._build_message(subject, body, [entrypoint], "request")

        return EventSourceResponse(
            self._runtime.submit_and_stream(message, timeout),
            ping=15000,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def _build_message(
        self,
        subject: str,
        body: str,
        targets: list[str],
        type: Literal["request", "response", "broadcast", "interrupt"] = "request",
    ) -> MAILMessage:
        """
        Build a MAIL message.
        """
        match type:
            case "request":
                if not len(targets) == 1:
                    raise ValueError("request messages must have exactly one target")
                target = targets[0]
                return MAILMessage(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                    message=MAILRequest(
                        task_id=str(uuid.uuid4()),
                        request_id=str(uuid.uuid4()),
                        sender=create_agent_address(self.user_id),
                        recipient=create_agent_address(target),
                        subject=subject,
                        body=body,
                        sender_swarm=self.swarm_name,
                        recipient_swarm=self.swarm_name,
                        routing_info={},
                    ),
                    msg_type="request",
                )
            case _:
                raise NotImplementedError(
                    f"type '{type}' not implemented for this method"
                )
