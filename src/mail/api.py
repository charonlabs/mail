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
from mail.swarm_registry import SwarmRegistry
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
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
    ) -> None:
        self.name = name
        self.factory = factory
        self.comm_targets = comm_targets
        self.enable_entrypoint = enable_entrypoint
        self.enable_interswarm = enable_interswarm
        self.agent_params = agent_params
        self.actions = self._build_actions()
        self.agent_function = self._build_agent_function(factory, agent_params)

    def _build_agent_function(
        self,
        factory: str,
        params: dict[str, Any],
    ) -> AgentFunction:
        return read_python_string(factory)(**params)

    def _build_actions(self) -> list["MAILAction"]:
        """
        Build the actions for the agent.
        """
        return [MAILAction.from_swarm_json(json.dumps(action)) for action in self.agent_params.get("actions", [])]

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILAgent":
        """
        Create a MAILAgent from a JSON dump following the `swarms.json` format.
        """
        REQUIRED_FIELDS = {
            "name": str,
            "factory": str,
            "comm_targets": list,
            "agent_params": dict,
        }
        OPTIONAL_FIELDS = {
            "actions": list,
            "enable_entrypoint": bool,
            "enable_interswarm": bool,
        }

        data = json.loads(json_dump)

        if data is None:
            raise ValueError("agent JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"agent JSON dump missing required field: '{field}'")
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(f"agent JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'")

        name = data["name"]
        factory = data["factory"]
        comm_targets = data["comm_targets"]
        agent_params = data["agent_params"]

        enable_entrypoint = data.get("enable_entrypoint", False)
        enable_interswarm = data.get("enable_interswarm", False)

        return MAILAgent(
            name=name,
            factory=factory,
            comm_targets=comm_targets,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
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
        self.description = description
        self.parameters = parameters
        self.function = self._build_action_function(function)

    def _build_action_function(
        self,
        function: str,
    ) -> ActionFunction:
        return read_python_string(function)

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILAction":
        """
        Create a MAILAction from a JSON dump following the `swarms.json` format.
        """
        REQUIRED_FIELDS = {
            "name": str,
            "description": str,
            "parameters": dict,
            "function": str,
        }
        
        data = json.loads(json_dump)
        
        if data is None:
            raise ValueError("action JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"action JSON dump missing required field: '{field}'")
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(f"action JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'")
        
        name = data["name"]
        description = data["description"]
        parameters = data["parameters"]
        function = data["function"]
                
        return MAILAction(
            name=name,
            description=description,
            parameters=parameters,
            function=function,
        )


class MAILSwarm:
    """
    Swarm instance class exposed via the MAIL API.
    """

    def __init__(
        self,
        swarm_name: str,
        agents: list[MAILAgent],
        actions: list[MAILAction],
        entrypoint: str,
        user_id: str = "default_user",
        swarm_registry: SwarmRegistry | None = None,
        enable_interswarm: bool = False,
    ) -> None:
        self.swarm_name = swarm_name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.user_id = user_id
        self._runtime = MAIL(
            agents={agent.name: agent.agent_function for agent in agents},
            actions={action.name: action.function for action in actions},
            user_id=user_id,
            swarm_name=swarm_name,
            swarm_registry=swarm_registry,
            enable_interswarm=enable_interswarm,
            entrypoint=entrypoint,
        )

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

        return await self.submit_message(message, timeout, show_events)


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

        return await self.submit_message_stream(message, timeout)

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

    async def shutdown(self) -> None:
        """
        Shut down the MAILSwarm.
        """
        await self._runtime.shutdown()

    async def start_interswarm(self) -> None:
        """
        Start interswarm messaging.
        """
        await self._runtime.start_interswarm()

    async def stop_interswarm(self) -> None:
        """
        Stop interswarm messaging.
        """
        await self._runtime.stop_interswarm()

    async def run_continuous(self) -> None:
        """
        Run the MAILSwarm in continuous mode.
        """
        await self._runtime.run_continuous()

    async def submit_message(
        self, 
        message: MAILMessage,
        timeout: float = 3600.0,
        show_events: bool = False,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Submit a fully-formed MAILMessage to the swarm and return the response.
        """
        response = await self._runtime.submit_and_wait(message, timeout)

        if show_events:
            return response, self._runtime.get_events_by_task_id(message["message"]["task_id"])
        else:
            return response, []

    async def submit_message_stream(
        self,
        message: MAILMessage,
        timeout: float = 3600.0,
    ) -> EventSourceResponse:
        """
        Submit a fully-formed MAILMessage to the swarm and stream the response.
        """
        return EventSourceResponse(
            self._runtime.submit_and_stream(message, timeout),
            ping=15000,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


class MAILSwarmTemplate:
    """
    Swarm template class exposed via the MAIL API.
    This class is used to create a swarm from a JSON dump or file.
    Unlike MAILSwarm, this class does not have a runtime.
    `MAILSwarmTemplate.instantiate()` creates a MAILSwarm containing a runtime.
    """

    def __init__(
        self,
        swarm_name: str,
        agents: list[MAILAgent],
        actions: list[MAILAction],
        entrypoint: str,
        enable_interswarm: bool = False,
    ) -> None:
        self.swarm_name = swarm_name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.enable_interswarm = enable_interswarm

    @staticmethod
    def _build_actions(agents: list[MAILAgent]) -> list[MAILAction]:
        """
        Build the actions for the swarm.
        """
        return [action for agent in agents for action in agent.actions]

    def instantiate(
        self,
        user_id: str = "default_user",
        base_url: str = "http://localhost:8000",
        registry_file: str | None = None,
    ) -> MAILSwarm:
        """
        Instantiate a MAILSwarm from a MAILSwarmTemplate.
        """
        if self.enable_interswarm:
            swarm_registry = SwarmRegistry(self.swarm_name, base_url, registry_file)
        else:
            swarm_registry = None
        return MAILSwarm(
            swarm_name=self.swarm_name,
            agents=self.agents,
            actions=self.actions,
            entrypoint=self.entrypoint,
            user_id=user_id,
            swarm_registry=swarm_registry,
            enable_interswarm=self.enable_interswarm,
        )

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILSwarmTemplate":
        """
        Create a MAILAbstractSwarm from a JSON dump following the `swarms.json` format.
        """
        REQUIRED_FIELDS = {
            "name": str,
            "agents": list,
            "entrypoint": str
        }
        OPTIONAL_FIELDS = {
            "enable_interswarm": bool
        }
        
        data = json.loads(json_dump)
        
        if data is None:
            raise ValueError("swarm JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"swarm JSON dump missing required field: '{field}'")
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(f"swarm JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'")
        
        name = data["name"]
        agents = [MAILAgent.from_swarm_json(json.dumps(agent)) for agent in data["agents"]]
        actions = MAILSwarmTemplate._build_actions(agents)
        entrypoint = data["entrypoint"]
        enable_interswarm = data.get("enable_interswarm", False)
                
        return MAILSwarmTemplate(
            swarm_name=name,
            agents=agents,
            actions=actions,
            entrypoint=entrypoint,
            enable_interswarm=enable_interswarm,
        )

    @staticmethod
    def from_swarm_json_file(json_filepath: str, swarm_name: str) -> "MAILSwarmTemplate":
        """
        Create a MAILSwarmTemplate from a JSON file following the `swarms.json` format.
        """
        with open(json_filepath, "r") as f:
            contents = f.read()
            full_json = json.loads(contents)
            for swarm in full_json:
                if swarm["name"] == swarm_name:
                    return MAILSwarmTemplate.from_swarm_json(json.dumps(swarm))
            raise ValueError(f"swarm '{swarm_name}' not found in {json_filepath}")

