import datetime
import json
import logging
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseConfig, BaseModel, ConfigDict, Field, create_model
from sse_starlette import EventSourceResponse, ServerSentEvent

from mail.core import MAIL
from mail.factories.action import ActionFunction
from mail.factories.base import AgentFunction
from mail.message import (
    MAILMessage,
    MAILRequest,
    create_agent_address,
    create_user_address,
)
from mail.swarm_registry import SwarmRegistry
from mail.tools import AgentToolCall, pydantic_model_to_tool
from mail.utils import read_python_string

logger = logging.getLogger("mail")


class MAILAgent:
    """
    Instance of an agent (including factory-built function) exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        function: AgentFunction,
        comm_targets: list[str],
        agent_params: dict[str, Any],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
    ) -> None:
        self.name = name
        self.function = function
        self.comm_targets = comm_targets
        self.enable_entrypoint = enable_entrypoint
        self.enable_interswarm = enable_interswarm
        self.agent_params = agent_params
        self.tool_format = tool_format

    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str = "required",
    ) -> tuple[str | None, list[AgentToolCall]]:
        return await self.function(messages, tool_choice)


class MAILAgentTemplate:
    """
    Template class for an agent in the MAIL API.
    """

    def __init__(
        self,
        name: str,
        factory: str,
        comm_targets: list[str],
        actions: list["MAILAction"],
        agent_params: dict[str, Any],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
    ) -> None:
        self.name = name
        self.factory = factory
        self.comm_targets = comm_targets
        self.actions = actions
        self.agent_params = agent_params
        self.enable_entrypoint = enable_entrypoint
        self.enable_interswarm = enable_interswarm
        self.tool_format = tool_format

    def _top_level_params(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "comm_targets": self.comm_targets,
            "tools": [action.to_tool_dict(style=self.tool_format) for action in self.actions],
            "enable_entrypoint": self.enable_entrypoint,
            "enable_interswarm": self.enable_interswarm,
            "tool_format": self.tool_format,
        }

    def instantiate(
        self,
        instance_params: dict[str, Any],
    ) -> MAILAgent:
        full_params = {**self._top_level_params(), **self.agent_params, **instance_params}
        factory = read_python_string(self.factory)
        agent_function = factory(**full_params)

        return MAILAgent(
            name=self.name,
            function=agent_function,
            comm_targets=self.comm_targets,
            agent_params=self.agent_params,
            enable_entrypoint=self.enable_entrypoint,
            enable_interswarm=self.enable_interswarm,
            tool_format=self.tool_format,
        )

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILAgentTemplate":
        """
        Create a MAILAgentTemplate from a JSON dump following the `swarms.json` format.
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
            "tool_format": Literal["completions", "responses"],
        }
        
        data = json.loads(json_dump)

        if data is None:
            raise ValueError("agent JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"agent JSON dump missing required field: '{field}'")
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(
                    f"agent JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'"
                )

        name = data["name"]
        factory = data["factory"]
        comm_targets = data["comm_targets"]
        actions = [MAILAction.from_swarm_json(json.dumps(action)) for action in data.get("actions", [])]
        agent_params = data["agent_params"]
        enable_entrypoint = data.get("enable_entrypoint", False)
        enable_interswarm = data.get("enable_interswarm", False)
        tool_format = data.get("tool_format", "responses")

        return MAILAgentTemplate(
            name=name,
            factory=factory,
            comm_targets=comm_targets,
            actions=actions,
            agent_params=agent_params,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            tool_format=tool_format,
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
                raise ValueError(
                    f"action JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'"
                )

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

    def to_tool_dict(
        self,
        style: Literal["completions", "responses"] = "responses",
    ) -> dict[str, Any]:
        """
        Convert the MAILAction to a tool dictionary.
        """
        return pydantic_model_to_tool(self.to_pydantic_model(for_tools=True), name=self.name, description=self.description, style=style)

    def to_pydantic_model(
        self,
        for_tools: bool = False,
    ) -> type[BaseModel]:
        """
        Convert the MAILAction to a Pydantic model.
        """
        if for_tools:
            parameters = self.parameters["properties"]
            assert isinstance(parameters, dict)

            fields = {key: Field(**parameters[key]) for key in parameters}
            for key in parameters:
                match parameters[key]["type"]:
                    case "string":
                        fields[key].annotation = str
                    case "integer":
                        fields[key].annotation = int
                    case "boolean":
                        fields[key].annotation = bool
                    case _:
                        raise ValueError(f"unsupported type: {parameters[key]['type']}")
                fields[key].json_schema_extra = None

            built_model = create_model("MAILActionBaseModelForTools", **{field_name: field.rebuild_annotation() for field_name, field in fields.items()})

            return built_model
        else:
            class MAILActionBaseModel(BaseModel):
                name: str = Field(description=self.name)
                description: str = Field(description=self.description)
                parameters: dict[str, Any] = Field()
                function: str = Field(description=str(self.function))

            return MAILActionBaseModel


class MAILSwarm:
    """
    Swarm instance class exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        agents: list[MAILAgent],
        actions: list[MAILAction],
        entrypoint: str,
        user_id: str = "default_user",
        swarm_registry: SwarmRegistry | None = None,
        enable_interswarm: bool = False,
    ) -> None:
        self.name = name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.user_id = user_id
        self._runtime = MAIL(
            agents={agent.name: agent.function for agent in agents},
            actions={action.name: action.function for action in actions},
            user_id=user_id,
            swarm_name=name,
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

        message = self._build_message(subject, body, [entrypoint], "user", "request")

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

        message = self._build_message(subject, body, [entrypoint], "user", "request")

        return await self.submit_message_stream(message, timeout)

    async def post_message_and_run(
        self,
        subject: str,
        body: str,
        entrypoint: str | None = None,
        show_events: bool = False,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Post a message to the swarm and run the swarm.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self._build_message(subject, body, [entrypoint], "user", "request")

        await self._runtime.submit(message)
        task_response = await self._runtime.run()

        if show_events:
            return task_response, self._runtime.get_events_by_task_id(
                task_response["message"]["task_id"]
            )
        else:
            return task_response, []

    def _build_message(
        self,
        subject: str,
        body: str,
        targets: list[str],
        sender_type: Literal["user", "agent"] = "user",
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
                        sender=create_user_address(self.user_id) if sender_type == "user" else create_agent_address(self.user_id),
                        recipient=create_agent_address(target),
                        subject=subject,
                        body=body,
                        sender_swarm=self.name,
                        recipient_swarm=self.name,
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
            return response, self._runtime.get_events_by_task_id(
                message["message"]["task_id"]
            )
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
        name: str,
        agents: list[MAILAgentTemplate],
        actions: list[MAILAction],
        entrypoint: str,
        enable_interswarm: bool = False,
    ) -> None:
        self.name = name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.enable_interswarm = enable_interswarm

    def instantiate(
        self,
        instance_params: dict[str, Any],
        user_id: str = "default_user",
        base_url: str = "http://localhost:8000",
        registry_file: str | None = None,
    ) -> MAILSwarm:
        """
        Instantiate a MAILSwarm from a MAILSwarmTemplate.
        """
        if self.enable_interswarm:
            swarm_registry = SwarmRegistry(self.name, base_url, registry_file)
        else:
            swarm_registry = None

        agents = [agent.instantiate(instance_params) for agent in self.agents]

        return MAILSwarm(
            name=self.name,
            agents=agents,
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
        REQUIRED_FIELDS = {"name": str, "agents": list, "entrypoint": str}
        OPTIONAL_FIELDS = {"enable_interswarm": bool}

        data = json.loads(json_dump)

        if data is None:
            raise ValueError("swarm JSON dump must not be None")
        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"swarm JSON dump missing required field: '{field}'")
            if not isinstance(data[field], REQUIRED_FIELDS[field]):
                raise ValueError(
                    f"swarm JSON dump field '{field}' must be of type '{REQUIRED_FIELDS[field].__name__}', not '{type(data[field]).__name__}'"
                )

        name = data["name"]
        agents = [
            MAILAgentTemplate.from_swarm_json(json.dumps(agent)) for agent in data["agents"]
        ]
        actions = [action for agent in agents for action in agent.actions]
        entrypoint = data["entrypoint"]
        enable_interswarm = data.get("enable_interswarm", False)

        return MAILSwarmTemplate(
            name=name,
            agents=agents,
            actions=actions,
            entrypoint=entrypoint,
            enable_interswarm=enable_interswarm,
        )

    @staticmethod
    def from_swarm_json_file(
        json_filepath: str, swarm_name: str
    ) -> "MAILSwarmTemplate":
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
