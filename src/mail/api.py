# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import datetime
import inspect
import logging
import uuid
from collections.abc import Callable
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model
from sse_starlette import EventSourceResponse, ServerSentEvent

from mail import utils
from mail.core import (
    ActionFunction,
    ActionOverrideFunction,
    AgentFunction,
    AgentToolCall,
    MAILMessage,
    MAILRequest,
    MAILRuntime,
    create_agent_address,
    create_user_address,
    pydantic_model_to_tool,
)
from mail.core.actions import ActionCore
from mail.core.agents import AgentCore
from mail.core.tools import MAIL_TOOL_NAMES
from mail.net import SwarmRegistry
from mail.net.router import StreamHandler
from mail.swarms_json import (
    SwarmsJSONAction,
    SwarmsJSONAgent,
    SwarmsJSONSwarm,
    build_action_from_swarms_json,
    build_agent_from_swarms_json,
    build_swarm_from_swarms_json,
    build_swarms_from_swarms_json,
    load_swarms_json_from_file,
)
from mail.utils import read_python_string, resolve_prefixed_string_references
from mail.factories.base import MAILAgentFunction

logger = logging.getLogger("mail")


class MAILAgent:
    """
    Instance of an agent (including factory-built function) exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        factory: str | Callable,
        actions: list["MAILAction"],
        function: AgentFunction,
        comm_targets: list[str],
        agent_params: dict[str, Any],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
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
        self.exclude_tools = exclude_tools
        self._validate()

    def _validate(self) -> None:
        """
        Validate an instance of the `MAILAgent` class.
        """
        if len(self.name) < 1:
            raise ValueError(
                f"agent name must be at least 1 character long, got {len(self.name)}"
            )
        if len(self.comm_targets) < 1 and (
            self.can_complete_tasks is False or self.enable_entrypoint is False
        ):
            raise ValueError(
                f"agent must have at least one communication target, got {len(self.comm_targets)}. If should be a solo agent, set can_complete_tasks and enable_entrypoint to True."
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
            exclude_tools=self.exclude_tools,
        )

    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str = "required",
    ) -> tuple[str | None, list[AgentToolCall]]:
        return await self.function(messages, tool_choice)

    def to_core(self) -> AgentCore:
        """
        Convert the `MAILAgent` to an `AgentCore`.
        """
        return AgentCore(
            function=self.function,
            comm_targets=self.comm_targets,
            actions={action.name: action.to_core() for action in self.actions},
            enable_entrypoint=self.enable_entrypoint,
            enable_interswarm=self.enable_interswarm,
            can_complete_tasks=self.can_complete_tasks,
        )


class MAILAgentTemplate:
    """
    Template class for an agent in the MAIL API.
    """

    def __init__(
        self,
        name: str,
        factory: str | Callable,
        comm_targets: list[str],
        actions: list["MAILAction"],
        agent_params: dict[str, Any],
        enable_entrypoint: bool = False,
        enable_interswarm: bool = False,
        can_complete_tasks: bool = False,
        tool_format: Literal["completions", "responses"] = "responses",
        exclude_tools: list[str] = [],
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
        self.exclude_tools = exclude_tools
        self._validate()

    def _validate(self) -> None:
        if len(self.name) < 1:
            raise ValueError(
                f"agent name must be at least 1 character long, got {len(self.name)}"
            )

    def _top_level_params(
        self, exclude_tools: list[str] | None = None
    ) -> dict[str, Any]:
        final_exclude = self.exclude_tools if exclude_tools is None else exclude_tools
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
            "exclude_tools": final_exclude,
        }

    def instantiate(
        self,
        instance_params: dict[str, Any],
        additional_exclude_tools: list[str] | None = None,
    ) -> MAILAgent:
        combined_exclude = sorted(
            set(self.exclude_tools + (additional_exclude_tools or []))
        )
        full_params = {
            **self._top_level_params(combined_exclude),
            **self.agent_params,
            **instance_params,
        }
        full_params["exclude_tools"] = combined_exclude
        if isinstance(self.factory, str):
            factory_func = read_python_string(self.factory)
        else:
            factory_func = self.factory
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
            exclude_tools=combined_exclude,
        )

    @staticmethod
    def from_swarms_json(
        agent_data: SwarmsJSONAgent,
        actions_by_name: dict[str, "MAILAction"] | None = None,
    ) -> "MAILAgentTemplate":
        """
        Create a MAILAgentTemplate from a pre-parsed `SwarmsJSONAgent` definition.
        """
        actions: list[MAILAction] = []
        action_names = agent_data.get("actions") or []
        if action_names:
            if not actions_by_name:
                raise ValueError(
                    f"agent '{agent_data['name']}' declares actions but no action definitions were provided"
                )
            for action_name in action_names:
                if action_name not in actions_by_name:
                    raise ValueError(
                        f"agent '{agent_data['name']}' references unknown action '{action_name}'"
                    )
                actions.append(actions_by_name[action_name])

        agent_params = resolve_prefixed_string_references(agent_data["agent_params"])
        return MAILAgentTemplate(
            name=agent_data["name"],
            factory=agent_data["factory"],
            comm_targets=agent_data["comm_targets"],
            actions=actions,
            agent_params=agent_params,
            enable_entrypoint=agent_data["enable_entrypoint"],
            enable_interswarm=agent_data["enable_interswarm"],
            tool_format=agent_data["tool_format"],
            can_complete_tasks=agent_data["can_complete_tasks"],
            exclude_tools=agent_data["exclude_tools"],
        )

    @staticmethod
    def from_swarm_json(
        json_dump: str,
        actions_by_name: dict[str, "MAILAction"] | None = None,
    ) -> "MAILAgentTemplate":
        """
        Create a MAILAgentTemplate from a JSON dump following the `swarms.json` format.
        """
        import json as _json

        agent_candidate = _json.loads(json_dump)
        parsed_agent = build_agent_from_swarms_json(agent_candidate)
        return MAILAgentTemplate.from_swarms_json(parsed_agent, actions_by_name)

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
                    exclude_tools=[],
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
                    exclude_tools=[],
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
                    exclude_tools=[],
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
                    exclude_tools=[],
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
                    exclude_tools=[],
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
        function: str | ActionFunction,
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
        function: str | ActionFunction,
    ) -> ActionFunction:
        if isinstance(function, str):
            return read_python_string(function)
        return function

    @staticmethod
    def from_pydantic_model(
        model: type[BaseModel],
        function: str | ActionFunction,
        name: str | None = None,
        description: str | None = None,
    ) -> "MAILAction":
        """
        Create a MAILAction from a Pydantic model and function string.
        """
        tool = pydantic_model_to_tool(
            model, name=name, description=description, style="responses"
        )
        return MAILAction(
            name=tool["name"],
            description=tool["description"],
            parameters=tool["parameters"],
            function=function,
        )

    def to_core(self) -> ActionCore:
        """
        Convert the MAILAction to an ActionCore.
        """
        return ActionCore(
            function=self.function,
            name=self.name,
            parameters=self.parameters,
        )

    @staticmethod
    def from_swarms_json(action_data: SwarmsJSONAction) -> "MAILAction":
        """
        Create a MAILAction from a pre-parsed `SwarmsJSONAction` definition.
        """
        return MAILAction(
            name=action_data["name"],
            description=action_data["description"],
            parameters=action_data["parameters"],
            function=action_data["function"],
        )

    @staticmethod
    def from_swarm_json(json_dump: str) -> "MAILAction":
        """
        Create a MAILAction from a JSON dump following the `swarms.json` format.
        """
        import json as _json

        action_candidate = _json.loads(json_dump)
        parsed_action = build_action_from_swarms_json(action_candidate)
        return MAILAction.from_swarms_json(parsed_action)

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
        breakpoint_tools: list[str] = [],
        exclude_tools: list[str] = [],
        task_message_limit: int | None = None,
    ) -> None:
        self.name = name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.user_id = user_id
        self.swarm_registry = swarm_registry
        self.enable_interswarm = enable_interswarm
        self.breakpoint_tools = breakpoint_tools
        self.exclude_tools = exclude_tools
        self.task_message_limit = task_message_limit
        self.adjacency_matrix, self.agent_names = self._build_adjacency_matrix()
        self.supervisors = [agent for agent in agents if agent.can_complete_tasks]
        self._agent_cores = {agent.name: agent.to_core() for agent in agents}
        self._runtime = MAILRuntime(
            agents=self._agent_cores,
            actions={action.name: action.to_core() for action in actions},
            user_id=user_id,
            swarm_name=name,
            swarm_registry=swarm_registry,
            enable_interswarm=enable_interswarm,
            entrypoint=entrypoint,
            breakpoint_tools=breakpoint_tools,
            exclude_tools=exclude_tools,
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

        # is each breakpoint tool valid?
        for tool in self.breakpoint_tools:
            if tool not in MAIL_TOOL_NAMES + [action.name for action in self.actions]:
                raise ValueError(f"breakpoint tool '{tool}' not found in swarm")

        # are the excluded tools valid?
        for tool in self.exclude_tools:
            if tool not in MAIL_TOOL_NAMES:
                raise ValueError(f"excluded tool '{tool}' is not valid")

    def _build_adjacency_matrix(self) -> tuple[list[list[int]], list[str]]:
        """
        Build an adjacency matrix for the swarm.
        Returns a tuple of the adjacency matrix and the map of indices to agent names.
        """
        agent_names = [agent.name for agent in self.agents]
        name_to_index = {name: idx for idx, name in enumerate(agent_names)}
        adj = [[0 for _ in agent_names] for _ in agent_names]

        for agent in self.agents:
            row_idx = name_to_index[agent.name]
            for target_name in agent.comm_targets:
                target_idx = name_to_index.get(target_name)
                if target_idx is not None:
                    adj[row_idx][target_idx] = 1

        return adj, agent_names

    def update_from_adjacency_matrix(self, adj: list[list[int]]) -> None:
        """
        Update `comm_targets` for all agents using an adjacency matrix.
        """

        if len(adj) != len(self.agents):
            raise ValueError(
                f"Length of adjacency matrix does not match number of agents. Expected: {len(self.agents)} Got: {len(adj)}"
            )

        idx_to_name = {idx: name for idx, name in enumerate(self.agent_names)}
        for i, agent_adj in enumerate(adj):
            if len(agent_adj) != len(adj):
                raise ValueError(
                    f"Adjacency matrix is malformed. Expected number of agents: {len(adj)} Got: {len(agent_adj)}"
                )

            target_idx = [j for j, x in enumerate(agent_adj) if x]
            new_targets = [idx_to_name[idx] for idx in target_idx]
            self.agents[i].comm_targets = new_targets

    async def post_message(
        self,
        body: str,
        subject: str = "New Message",
        msg_type: Literal["request", "response", "broadcast", "interrupt"] = "request",
        entrypoint: str | None = None,
        show_events: bool = False,
        timeout: float = 3600.0,
        task_id: str | None = None,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Post a message to the swarm and return the task completion response.
        This method is indented to be used when the swarm is running in continuous mode.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self.build_message(
            subject, body, [entrypoint], "user", msg_type, task_id
        )
        task_id = message["message"]["task_id"]

        runtime_kwargs = dict(kwargs)
        if resume_from is not None:
            runtime_kwargs["resume_from"] = resume_from

        return await self.submit_message(
            message,
            timeout=timeout,
            show_events=show_events,
            **runtime_kwargs,
        )

    async def post_message_stream(
        self,
        body: str,
        subject: str = "New Message",
        msg_type: Literal["request", "response", "broadcast", "interrupt"] = "request",
        entrypoint: str | None = None,
        task_id: str | None = None,
        timeout: float = 3600.0,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> EventSourceResponse:
        """
        Post a message to the swarm and stream the response.
        This method is indented to be used when the swarm is running in continuous mode.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self.build_message(
            subject, body, [entrypoint], "user", msg_type, task_id
        )

        runtime_kwargs = dict(kwargs)
        if resume_from is not None:
            runtime_kwargs["resume_from"] = resume_from

        return await self.submit_message_stream(
            message,
            timeout=timeout,
            **runtime_kwargs,
        )

    async def post_message_and_run(
        self,
        body: str,
        subject: str = "New Message",
        msg_type: Literal["request", "response", "broadcast", "interrupt"] = "request",
        entrypoint: str | None = None,
        show_events: bool = False,
        task_id: str | None = None,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        max_steps: int | None = None,
        **kwargs: Any,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Post a message to the swarm and run until the task is complete.
        This method cannot be used when the swarm is running in continuous mode.
        """
        if entrypoint is None:
            entrypoint = self.entrypoint

        message = self.build_message(
            subject, body, [entrypoint], "user", msg_type, task_id
        )
        task_id = message["message"]["task_id"]

        await self._runtime.submit(message)
        task_response = await self._runtime.run_task(
            task_id=task_id, resume_from=resume_from, max_steps=max_steps, **kwargs
        )

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
        task_id: str | None = None,
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
                        task_id=task_id or str(uuid.uuid4()),
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
        if self.enable_interswarm and self.swarm_registry is not None:
            await self.swarm_registry.stop_health_checks()

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

        await self.swarm_registry.start_health_checks()
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
        max_steps: int | None = None,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        Run the MAILSwarm in continuous mode.
        """
        await self._runtime.run_continuous(max_steps, action_override)

    async def submit_message(
        self,
        message: MAILMessage,
        timeout: float = 3600.0,
        show_events: bool = False,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> tuple[MAILMessage, list[ServerSentEvent]]:
        """
        Submit a fully-formed MAILMessage to the swarm and return the response.
        """
        response = await self._runtime.submit_and_wait(
            message, timeout, resume_from, **kwargs
        )

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
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        *,
        ping_interval: int | None = 15000,
        **kwargs: Any,
    ) -> EventSourceResponse:
        """
        Submit a fully-formed MAILMessage to the swarm and stream the response.
        """
        # Support runtimes that either return an async generator directly
        # or coroutines that resolve to an async generator.
        maybe_stream = self._runtime.submit_and_stream(
            message, timeout, resume_from, **kwargs
        )
        stream = (
            await maybe_stream  # type: ignore[func-returns-value]
            if inspect.isawaitable(maybe_stream)
            else maybe_stream
        )

        return EventSourceResponse(
            stream,
            ping=ping_interval,
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

    async def route_interswarm_message(
        self,
        message: MAILMessage,
        *,
        stream_handler: StreamHandler | None = None,
        ignore_stream_pings: bool = False,
    ) -> MAILMessage:
        """
        Route an interswarm message to the appropriate destination.
        """
        router = self._runtime.interswarm_router
        if router is None:
            raise ValueError("interswarm router not available")

        return await router.route_message(
            message,
            stream_handler=stream_handler,
            ignore_stream_pings=ignore_stream_pings,
        )

    def get_subswarm(
        self, names: list[str], name_suffix: str, entrypoint: str | None = None
    ) -> "MAILSwarmTemplate":
        """
        Get a subswarm of the current swarm. Only agents with names in the `names` list will be included.
        Returns a `MAILSwarmTemplate`.
        """
        agent_lookup = {agent.name: agent for agent in self.agents}
        selected_agents: list[MAILAgentTemplate] = []
        for agent_name in names:
            if agent_name not in agent_lookup:
                raise ValueError(f"agent '{agent_name}' not found in swarm")
            agent = agent_lookup[agent_name]
            filtered_targets = [
                target for target in agent.comm_targets if target in names
            ]
            if agent.name in filtered_targets:
                filtered_targets.remove(agent.name)
            if not filtered_targets:
                fallback_candidates = [n for n in names if n != agent.name]
                if fallback_candidates:
                    filtered_targets = [fallback_candidates[0]]
                else:
                    filtered_targets = [agent.name]
            selected_agents.append(
                MAILAgentTemplate(
                    name=agent.name,
                    factory=agent.factory,
                    comm_targets=filtered_targets,
                    actions=agent.actions,
                    agent_params=deepcopy(agent.agent_params),
                    enable_entrypoint=agent.enable_entrypoint,
                    enable_interswarm=agent.enable_interswarm,
                    can_complete_tasks=agent.can_complete_tasks,
                    tool_format=agent.tool_format,
                    exclude_tools=agent.exclude_tools,
                )
            )

        if entrypoint is None:
            entrypoint_agent = next(
                (agent for agent in selected_agents if agent.enable_entrypoint), None
            )
            if entrypoint_agent is None:
                raise ValueError("Subswarm must contain an entrypoint agent")
        else:
            entrypoint_agent = next(
                (agent for agent in selected_agents if agent.name == entrypoint), None
            )
            if entrypoint_agent is None:
                raise ValueError(f"entrypoint agent '{entrypoint}' not found in swarm")
            entrypoint_agent.enable_entrypoint = True

        if not any(agent.can_complete_tasks for agent in selected_agents):
            raise ValueError("Subswarm must contain at least one supervisor")

        actions: list[MAILAction] = []
        seen_actions: dict[str, MAILAction] = {}
        for agent_template in selected_agents:
            for action in agent_template.actions:
                if action.name not in seen_actions:
                    seen_actions[action.name] = action
        actions = list(seen_actions.values())

        return MAILSwarmTemplate(
            name=f"{self.name}-{name_suffix}",
            agents=selected_agents,
            actions=actions,
            entrypoint=entrypoint_agent.name,
            enable_interswarm=self.enable_interswarm,
        )

    def get_response_message(self, task_id: str) -> MAILMessage | None:
        """Get the response message for a given task ID. Mostly used after streaming response events."""
        return self._runtime.get_response_message(task_id)

    def get_events(self, task_id: str) -> list[ServerSentEvent]:
        """Get the events for a given task ID. Mostly used after streaming response events."""
        return self._runtime.get_events_by_task_id(task_id)


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
        breakpoint_tools: list[str] = [],
        exclude_tools: list[str] = [],
        task_message_limit: int | None = None,
    ) -> None:
        self.name = name
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.enable_interswarm = enable_interswarm
        self.breakpoint_tools = breakpoint_tools
        self.exclude_tools = exclude_tools
        self.task_message_limit = task_message_limit
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

        # is each breakpoint tool valid?
        for tool in self.breakpoint_tools:
            if tool not in MAIL_TOOL_NAMES + [action.name for action in self.actions]:
                raise ValueError(f"breakpoint tool '{tool}' not found in swarm")

        # are the excluded tools valid?
        for tool in self.exclude_tools:
            if tool not in MAIL_TOOL_NAMES:
                raise ValueError(f"excluded tool '{tool}' is not valid")

    def _build_adjacency_matrix(self) -> tuple[list[list[int]], list[str]]:
        """
        Build an adjacency matrix for the swarm.
        Returns a tuple of the adjacency matrix and the map of agent names to indices.
        """
        agent_names = [agent.name for agent in self.agents]
        name_to_index = {name: idx for idx, name in enumerate(agent_names)}
        adj = [[0 for _ in agent_names] for _ in agent_names]

        for agent in self.agents:
            row_idx = name_to_index[agent.name]
            for target_name in agent.comm_targets:
                target_idx = name_to_index.get(target_name)
                if target_idx is not None:
                    adj[row_idx][target_idx] = 1

        return adj, agent_names

    def update_from_adjacency_matrix(self, adj: list[list[int]]) -> None:
        """
        Update comm_targets for all agents using an adjacency matrix.
        """

        if len(adj) != len(self.agents):
            raise ValueError(
                f"Length of adjacency matrix does not match number of agents. Expected: {len(self.agents)} Got: {len(adj)}"
            )

        idx_to_name = {idx: name for idx, name in enumerate(self.agent_names)}
        for i, agent_adj in enumerate(adj):
            if len(agent_adj) != len(adj):
                raise ValueError(
                    f"Adjacency matrix is malformed. Expected number of agents: {len(adj)} Got: {len(agent_adj)}"
                )

            target_idx = [j for j, x in enumerate(agent_adj) if x]
            new_targets = [idx_to_name[idx] for idx in target_idx]
            self.agents[i].comm_targets = new_targets

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

        agents = [
            agent.instantiate(
                instance_params, additional_exclude_tools=self.exclude_tools
            )
            for agent in self.agents
        ]

        for agent in agents:
            delimiter = "Here are details about the agents you can communicate with:"
            prompt = agent.agent_params["system"]
            if delimiter in prompt:
                lines = prompt.splitlines()
                result_lines = []
                for line in lines:
                    if delimiter in line:
                        break
                    result_lines.append(line)
                prompt = '\n'.join(result_lines)
                prompt += f"\n\n{delimiter}\n\n"
            else:
                prompt += f"\n\n{delimiter}\n\n"
            targets_as_agents = [a for a in agents if a.name in agent.comm_targets]
            for t in targets_as_agents:
                prompt += f"Name: {t.name}\n"
                prompt += f"Capabilities:\n"
                function = t.function
                if isinstance(function, MAILAgentFunction):
                    if "web_search" in function.tools and "code_interpreter" in function.tools:
                        prompt += "- This agent can search the web\n- This agent can execute code. The code it writes cannot access the internet."
                    if "web_search" in function.tools and "code_interpreter" not in function.tools:
                        prompt += "- This agent can search the web\n- This agent cannot execute code"
                    if "web_search" not in function.tools and "code_interpreter" in function.tools:
                        prompt += "- This agent can execute code. The code it writes cannot access the internet.\n- This agent cannot search the web"
                    if "web_search" not in function.tools and "code_interpreter" not in function.tools:
                        prompt += "- This agent does not have access to tools, the internet, real-time data, etc."
                else:
                    prompt += "- This agent does not have access to tools, the internet, real-time data, etc."
                prompt += "\n\n"
            prompt.strip()

        return MAILSwarm(
            name=self.name,
            agents=agents,
            actions=self.actions,
            entrypoint=self.entrypoint,
            user_id=user_id,
            swarm_registry=swarm_registry,
            enable_interswarm=self.enable_interswarm,
            breakpoint_tools=self.breakpoint_tools,
            exclude_tools=self.exclude_tools,
            task_message_limit=self.task_message_limit,
        )

    def get_subswarm(
        self, names: list[str], name_suffix: str, entrypoint: str | None = None
    ) -> "MAILSwarmTemplate":
        """
        Get a subswarm of the current swarm. Only agents with names in the `names` list will be included.
        Returns a `MAILSwarmTemplate`.
        """
        agent_lookup = {agent.name: agent for agent in self.agents}
        selected_agents: list[MAILAgentTemplate] = []
        for agent_name in names:
            if agent_name not in agent_lookup:
                raise ValueError(f"agent '{agent_name}' not found in swarm")
            agent = agent_lookup[agent_name]
            filtered_targets = [
                target for target in agent.comm_targets if target in names
            ]
            if agent.name in filtered_targets:
                filtered_targets.remove(agent.name)
            if not filtered_targets:
                fallback_candidates = [n for n in names if n != agent.name]
                if fallback_candidates:
                    filtered_targets = [fallback_candidates[0]]
                else:
                    filtered_targets = [agent.name]
            selected_agents.append(
                MAILAgentTemplate(
                    name=agent.name,
                    factory=agent.factory,
                    comm_targets=filtered_targets,
                    actions=agent.actions,
                    agent_params=deepcopy(agent.agent_params),
                    enable_entrypoint=agent.enable_entrypoint,
                    enable_interswarm=agent.enable_interswarm,
                    can_complete_tasks=agent.can_complete_tasks,
                    tool_format=agent.tool_format,
                    exclude_tools=agent.exclude_tools,
                )
            )

        if entrypoint is None:
            entrypoint_agent = next(
                (agent for agent in selected_agents if agent.enable_entrypoint), None
            )
            if entrypoint_agent is None:
                raise ValueError("Subswarm must contain an entrypoint agent")
        else:
            entrypoint_agent = next(
                (agent for agent in selected_agents if agent.name == entrypoint), None
            )
            if entrypoint_agent is None:
                raise ValueError(f"entrypoint agent '{entrypoint}' not found in swarm")
            entrypoint_agent.enable_entrypoint = True

        if not any(agent.can_complete_tasks for agent in selected_agents):
            raise ValueError("Subswarm must contain at least one supervisor")

        actions: list[MAILAction] = []
        seen_actions: dict[str, MAILAction] = {}
        for agent_template in selected_agents:
            for action in agent_template.actions:
                if action.name not in seen_actions:
                    seen_actions[action.name] = action
        actions = list(seen_actions.values())

        return MAILSwarmTemplate(
            name=f"{self.name}-{name_suffix}",
            agents=selected_agents,
            actions=actions,
            entrypoint=entrypoint_agent.name,
            enable_interswarm=self.enable_interswarm,
            breakpoint_tools=self.breakpoint_tools,
            exclude_tools=self.exclude_tools,
        )

    @staticmethod
    def from_swarms_json(
        swarm_data: SwarmsJSONSwarm, task_message_limit: int | None = None
    ) -> "MAILSwarmTemplate":
        """
        Create a `MAILSwarmTemplate` from a pre-parsed `SwarmsJSONSwarm` definition.
        """
        actions = [
            MAILAction.from_swarms_json(action) for action in swarm_data["actions"]
        ]
        actions_by_name = {action.name: action for action in actions}
        agents = [
            MAILAgentTemplate.from_swarms_json(agent, actions_by_name)
            for agent in swarm_data["agents"]
        ]

        return MAILSwarmTemplate(
            name=swarm_data["name"],
            agents=agents,
            actions=actions,
            entrypoint=swarm_data["entrypoint"],
            enable_interswarm=swarm_data["enable_interswarm"],
            breakpoint_tools=swarm_data["breakpoint_tools"],
            exclude_tools=swarm_data["exclude_tools"],
            task_message_limit=task_message_limit,
        )

    @staticmethod
    def from_swarm_json(
        json_dump: str, task_message_limit: int | None = None
    ) -> "MAILSwarmTemplate":
        """
        Create a `MAILSwarmTemplate` from a JSON dump following the `swarms.json` format.
        """
        import json as _json

        swarm_candidate = _json.loads(json_dump)
        parsed_swarm = build_swarm_from_swarms_json(swarm_candidate)
        return MAILSwarmTemplate.from_swarms_json(parsed_swarm, task_message_limit)

    @staticmethod
    def from_swarm_json_file(
        swarm_name: str,
        json_filepath: str = "swarms.json",
        task_message_limit: int | None = None,
    ) -> "MAILSwarmTemplate":
        """
        Create a `MAILSwarmTemplate` from a JSON file following the `swarms.json` format.
        """
        swarms_file = load_swarms_json_from_file(json_filepath)
        swarms = build_swarms_from_swarms_json(swarms_file["swarms"])
        for swarm in swarms:
            if swarm["name"] == swarm_name:
                return MAILSwarmTemplate.from_swarms_json(swarm, task_message_limit)
        raise ValueError(f"swarm '{swarm_name}' not found in {json_filepath}")
