import asyncio
import datetime
import inspect
import json
import logging
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model
from sse_starlette import EventSourceResponse, ServerSentEvent

from mail import utils
from mail.core import (
    AgentToolCall,
    MAILMessage,
    MAILRequest,
    MAILRuntime,
    create_agent_address,
    create_user_address,
    pydantic_model_to_tool,
)
from mail.factories.action import ActionFunction, ActionOverrideFunction
from mail.factories.base import AgentFunction
from mail.net import SwarmRegistry
from mail.utils import read_python_string

logger = logging.getLogger("mail")


class MAILAgent:
    """
    Instance of an agent (including factory-built function) exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        factory: str,
        actions: list["MAILAction"],
        function: AgentFunction,
        comm_targets: list[str],
        agent_params: dict[str, Any],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
    ) -> None:
        self.name = name
        self.factory = factory
        self.actions = actions
        self.function = function
        self.comm_targets = comm_targets
        self.enable_entrypoint = enable_entrypoint
        self.enable_interswarm = enable_interswarm
        self.agent_params = agent_params
        self.tool_format = tool_format
        self.can_complete_tasks = can_complete_tasks
        self._validate()

    def _validate(self) -> None:
        """
        Validate an instance of the `MAILAgent` class.
        """
        if len(self.name) < 1:
            raise ValueError(
                f"agent name must be at least 1 character long, got {len(self.name)}"
            )
        if len(self.comm_targets) < 1:
            raise ValueError(
                f"agent must have at least one communication target, got {len(self.comm_targets)}"
            )

    def _to_template(self, names: list[str]) -> "MAILAgentTemplate":
        """
        Convert the MAILAgent to a MAILAgentTemplate.
        The names parameter is used to filter comm targets.
        """
        return MAILAgentTemplate(
            name=self.name,
            factory=self.factory,
            comm_targets=[target for target in self.comm_targets if target in names],
            actions=self.actions,
            agent_params=self.agent_params,
            enable_entrypoint=self.enable_entrypoint,
            enable_interswarm=self.enable_interswarm,
            tool_format=self.tool_format,
            can_complete_tasks=self.can_complete_tasks,
        )

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
        can_complete_tasks: bool = False,
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
        self.can_complete_tasks = can_complete_tasks
        self._validate()

    def _validate(self) -> None:
        if len(self.name) < 1:
            raise ValueError(
                f"agent name must be at least 1 character long, got {len(self.name)}"
            )
        if len(self.comm_targets) < 1:
            raise ValueError(
                f"agent must have at least one communication target, got {len(self.comm_targets)}"
            )

    def _top_level_params(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "comm_targets": self.comm_targets,
            "tools": [
                action.to_tool_dict(style=self.tool_format) for action in self.actions
            ],
            "enable_entrypoint": self.enable_entrypoint,
            "enable_interswarm": self.enable_interswarm,
            "tool_format": self.tool_format,
            "can_complete_tasks": self.can_complete_tasks,
        }

    def instantiate(
        self,
        instance_params: dict[str, Any],
    ) -> MAILAgent:
        full_params = {
            **self._top_level_params(),
            **self.agent_params,
            **instance_params,
        }
        factory_func = read_python_string(self.factory)
        agent_function = factory_func(**full_params)

        return MAILAgent(
            name=self.name,
            factory=self.factory,
            actions=self.actions,
            function=agent_function,
            comm_targets=self.comm_targets,
            agent_params=self.agent_params,
            enable_entrypoint=self.enable_entrypoint,
            enable_interswarm=self.enable_interswarm,
            tool_format=self.tool_format,
            can_complete_tasks=self.can_complete_tasks,
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
            "can_complete_tasks": bool,
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
        actions = [
            MAILAction.from_swarm_json(json.dumps(action))
            for action in data.get("actions", [])
        ]
        agent_params = data["agent_params"]
        enable_entrypoint = data.get("enable_entrypoint", False)
        enable_interswarm = data.get("enable_interswarm", False)
        tool_format = data.get("tool_format", "responses")
        can_complete_tasks = data.get("can_complete_tasks", False)

        return MAILAgentTemplate(
            name=name,
            factory=factory,
            comm_targets=comm_targets,
            actions=actions,
            agent_params=agent_params,
            enable_entrypoint=enable_entrypoint,
            enable_interswarm=enable_interswarm,
            tool_format=tool_format,
            can_complete_tasks=can_complete_tasks,
        )

    @staticmethod
    def from_example(
        name: Literal["supervisor", "weather", "math", "consultant", "analyst"],
        comm_targets: list[str],
    ) -> "MAILAgentTemplate":
        """
        Create a MAILAgent from an example in `mail.examples`.
        """
        match name:
            case "supervisor":
                from mail.examples import supervisor
                from mail.factories import supervisor_factory

                agent_params = supervisor.supervisor_agent_params

                return MAILAgentTemplate(
                    name=name,
                    factory=supervisor_factory.__name__,
                    comm_targets=comm_targets,
                    actions=[],
                    agent_params=agent_params,
                    enable_entrypoint=True,
                    enable_interswarm=False,
                    tool_format="responses",
                    can_complete_tasks=True,
                )
            case "weather":
                from mail.examples import weather_dummy as weather

                agent_params = weather.weather_agent_params
                actions = [weather.action_get_weather_forecast]

                return MAILAgentTemplate(
                    name=name,
                    factory=weather.factory_weather_dummy.__name__,
                    comm_targets=comm_targets,
                    actions=actions,
                    agent_params=agent_params,
                    enable_entrypoint=False,
                    enable_interswarm=False,
                    tool_format="responses",
                    can_complete_tasks=False,
                )
            case "math":
                from mail.examples import math_dummy as math

                agent_params = math.math_agent_params

                return MAILAgentTemplate(
                    name=name,
                    factory=math.factory_math_dummy.__name__,
                    comm_targets=comm_targets,
                    actions=[],
                    agent_params=agent_params,
                    enable_entrypoint=False,
                    enable_interswarm=False,
                    tool_format="responses",
                    can_complete_tasks=False,
                )
            case "consultant":
                from mail.examples import consultant_dummy as consultant

                agent_params = consultant.consultant_agent_params

                return MAILAgentTemplate(
                    name=name,
                    factory=consultant.factory_consultant_dummy.__name__,
                    comm_targets=comm_targets,
                    actions=[],
                    agent_params=agent_params,
                    enable_entrypoint=False,
                    enable_interswarm=False,
                    tool_format="responses",
                    can_complete_tasks=False,
                )
            case "analyst":
                from mail.examples import analyst_dummy as analyst

                agent_params = analyst.analyst_agent_params

                return MAILAgentTemplate(
                    name=name,
                    factory=analyst.factory_analyst_dummy.__name__,
                    comm_targets=comm_targets,
                    actions=[],
                    agent_params=agent_params,
                    enable_entrypoint=False,
                    enable_interswarm=False,
                    tool_format="responses",
                    can_complete_tasks=False,
                )
            case _:
                raise ValueError(f"invalid agent name: {name}")


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
        self._validate()

    def _validate(self) -> None:
        """
        Validate an instance of the `MAILAction` class.
        """
        if len(self.name) < 1:
            raise ValueError(
                f"action name must be at least 1 character long, got {len(self.name)}"
            )
        if len(self.description) < 1:
            raise ValueError(
                f"action description must be at least 1 character long, got {len(self.description)}"
            )

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
        return pydantic_model_to_tool(
            self.to_pydantic_model(for_tools=True),
            name=self.name,
            description=self.description,
            style=style,
        )

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

            built_model = create_model(
                "MAILActionBaseModelForTools",
                **{
                    field_name: field.rebuild_annotation()
                    for field_name, field in fields.items()
                },
            )

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
        self.swarm_registry = swarm_registry
        self.enable_interswarm = enable_interswarm
        self.adjacency_matrix, self.agent_names = self._build_adjacency_matrix()
        self.supervisors = [agent for agent in agents if agent.can_complete_tasks]
        self._runtime = MAILRuntime(
            agents={agent.name: agent.function for agent in agents},
            actions={action.name: action.function for action in actions},
            user_id=user_id,
            swarm_name=name,
            swarm_registry=swarm_registry,
            enable_interswarm=enable_interswarm,
            entrypoint=entrypoint,
        )
        self._validate()

    def _validate(self) -> None:
        """
        Validate an instance of the `MAILSwarm` class.
        """
        if len(self.name) < 1:
            raise ValueError(
                f"swarm name must be at least 1 character long, got {len(self.name)}"
            )
        if len(self.agents) < 1:
            raise ValueError(
                f"swarm must have at least one agent, got {len(self.agents)}"
            )
        if len(self.user_id) < 1:
            raise ValueError(
                f"user ID must be at least 1 character long, got {len(self.user_id)}"
            )

        # is the entrypoint valid?
        entrypoints = [agent.name for agent in self.agents if agent.enable_entrypoint]
        if len(entrypoints) < 1:
            raise ValueError(
                f"swarm must have at least one entrypoint agent, got {len(entrypoints)}"
            )
        if self.entrypoint not in entrypoints:
            raise ValueError(f"entrypoint agent '{self.entrypoint}' not found in swarm")

        # are agent comm targets valid?
        for agent in self.agents:
            for target in agent.comm_targets:
                interswarm_target = utils.target_address_is_interswarm(target)
                if interswarm_target and not self.enable_interswarm:
                    raise ValueError(
                        f"agent '{agent.name}' has interswarm communication target '{target}' but interswarm messaging is not enabled for this swarm"
                    )
                if not interswarm_target and target not in [
                    agent.name for agent in self.agents
                ]:
                    raise ValueError(
                        f"agent '{agent.name}' has invalid communication target '{target}'"
                    )

        if self.swarm_registry is None and self.enable_interswarm:
            raise ValueError(
                "swarm registry must be provided if interswarm messaging is enabled"
            )

        # is there at least one supervisor?
        if len(self.supervisors) < 1:
            raise ValueError(
                f"swarm must have at least one supervisor, got {len(self.supervisors)}"
            )

    def _build_adjacency_matrix(self) -> tuple[list[list[int]], list[str]]:
        """
        Build an adjacency matrix for the swarm.
        Returns a tuple of the adjacency matrix and the map of indices to agent names.
        """
        adj = []
        map = []
        for agent in self.agents:
            map.append(agent.name)
            adj.append(
                [1 if target in agent.comm_targets else 0 for target in self.agents]
            )

        return adj, map

    async def post_message(
        self,
        body: str,
        subject: str = "New Message",
        entrypoint: str | None = None,
        show_events: bool = False,
        timeout: float = 3600.0,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Post a message to the swarm and return the task completion response.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self.build_message(subject, body, [entrypoint], "user", "request")

        return await self.submit_message(message, timeout, show_events)

    async def post_message_stream(
        self,
        body: str,
        subject: str = "New Message",
        entrypoint: str | None = None,
        timeout: float = 3600.0,
    ) -> EventSourceResponse:
        """
        Post a message to the swarm and stream the response.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self.build_message(subject, body, [entrypoint], "user", "request")

        return await self.submit_message_stream(message, timeout)

    async def post_message_and_run(
        self,
        body: str,
        subject: str = "New Message",
        entrypoint: str | None = None,
        show_events: bool = False,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Post a message to the swarm and run the swarm.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self.build_message(subject, body, [entrypoint], "user", "request")

        await self._runtime.submit(message)
        task_response = await self._runtime.run()

        if show_events:
            return task_response, self._runtime.get_events_by_task_id(
                task_response["message"]["task_id"]
            )
        else:
            return task_response, []

    def build_message(
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
                        sender=create_user_address(self.user_id)
                        if sender_type == "user"
                        else create_agent_address(self.user_id),
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
        if not self.enable_interswarm:
            raise ValueError("interswarm messaging is not enabled for this swarm")
        if self.swarm_registry is None:
            raise ValueError(
                "swarm registry must be provided if interswarm messaging is enabled"
            )

        await self._runtime.start_interswarm()

    async def stop_interswarm(self) -> None:
        """
        Stop interswarm messaging.
        """
        if not self.enable_interswarm:
            raise ValueError("interswarm messaging is not enabled for this swarm")
        if self.swarm_registry is None:
            raise ValueError(
                "swarm registry must be provided if interswarm messaging is enabled"
            )

        await self._runtime.stop_interswarm()

    async def is_interswarm_running(self) -> bool:
        """
        Check if interswarm messaging is running.
        """
        if not self.enable_interswarm:
            return False
        if self.swarm_registry is None:
            return False

        return await self._runtime.is_interswarm_running()

    async def run_continuous(
        self,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        Run the MAILSwarm in continuous mode.
        """
        await self._runtime.run_continuous(action_override)

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
        # Support runtimes that either return an async generator directly
        # or coroutines that resolve to an async generator.
        maybe_stream = self._runtime.submit_and_stream(message, timeout)
        stream = (
            await maybe_stream  # type: ignore[func-returns-value]
            if inspect.isawaitable(maybe_stream)
            else maybe_stream
        )

        return EventSourceResponse(
            stream,
            ping=15000,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def handle_interswarm_response(self, response_message: MAILMessage) -> None:
        """
        Handle an incoming response from a remote swarm.
        """
        await self._runtime.handle_interswarm_response(response_message)

    def get_pending_requests(self) -> dict[str, asyncio.Future[MAILMessage]]:
        """
        Get the pending requests for the swarm.
        """
        return self._runtime.pending_requests

    async def route_interswarm_message(self, message: MAILMessage) -> MAILMessage:
        """
        Route an interswarm message to the appropriate destination.
        """
        router = self._runtime.interswarm_router
        if router is None:
            raise ValueError("interswarm router not available")

        return await router.route_message(message)

    def get_subswarm(self, swarm_name: str, names: list[str]) -> "MAILSwarmTemplate":
        """
        Get a subswarm of the MAILSwarm.
        """
        for n in names:
            if n not in self.agent_names:
                raise ValueError(f"agent '{n}' not found in swarm")
        names_to_og_idx = {n: i for i, n in enumerate(self.agent_names)}
        return MAILSwarmTemplate(
            name=swarm_name,
            agents=[self.agents[names_to_og_idx[n]]._to_template(names) for n in names],
            actions=self.actions,
            entrypoint=self.entrypoint,
            enable_interswarm=self.enable_interswarm,
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
        self.adjacency_matrix, self.agent_names = self._build_adjacency_matrix()
        self.supervisors = [agent for agent in agents if agent.can_complete_tasks]
        self._validate()

    def _validate(self) -> None:
        """
        Validate an instance of the `MAILSwarmTemplate` class.
        """
        if len(self.name) < 1:
            raise ValueError(
                f"swarm name must be at least 1 character long, got {len(self.name)}"
            )
        if len(self.agents) < 1:
            raise ValueError(
                f"swarm must have at least one agent, got {len(self.agents)}"
            )

        # is the entrypoint valid?
        entrypoints = [agent.name for agent in self.agents if agent.enable_entrypoint]
        if len(entrypoints) < 1:
            raise ValueError(
                f"swarm must have at least one entrypoint agent, got {len(entrypoints)}"
            )
        if self.entrypoint not in entrypoints:
            raise ValueError(f"entrypoint agent '{self.entrypoint}' not found in swarm")

        # are agent comm targets valid?
        agent_names = [agent.name for agent in self.agents]
        for agent in self.agents:
            for target in agent.comm_targets:
                interswarm_target = utils.target_address_is_interswarm(target)
                if interswarm_target and not self.enable_interswarm:
                    raise ValueError(
                        f"agent '{agent.name}' has interswarm communication target '{target}' but interswarm messaging is not enabled for this swarm"
                    )
                if not interswarm_target and target not in agent_names:
                    raise ValueError(
                        f"agent '{agent.name}' has invalid communication target '{target}'"
                    )

        # is there at least one supervisor?
        if len(self.supervisors) < 1:
            raise ValueError(
                f"swarm must have at least one supervisor, got {len(self.supervisors)}"
            )

    def _build_adjacency_matrix(self) -> tuple[list[list[int]], list[str]]:
        """
        Build an adjacency matrix for the swarm.
        Returns a tuple of the adjacency matrix and the map of agent names to indices.
        """
        adj = []
        map = []
        for agent in self.agents:
            map.append(agent.name)
            adj.append(
                [1 if target in agent.comm_targets else 0 for target in self.agents]
            )

        return adj, map

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
            MAILAgentTemplate.from_swarm_json(json.dumps(agent))
            for agent in data["agents"]
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
        swarm_name: str,
        json_filepath: str = "swarms.json",
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
