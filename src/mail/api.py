# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import datetime
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from functools import wraps
from typing import Any, Literal, TypeVar, get_type_hints

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
    create_admin_address,
    create_agent_address,
    create_user_address,
    pydantic_model_to_tool,
)
from mail.core.actions import ActionCore
from mail.core.agents import AgentCore
from mail.core.message import MAILBroadcast, MAILInterswarmMessage
from mail.core.tasks import MAILTask
from mail.core.tools import MAIL_TOOL_NAMES
from mail.factories.base import MAILAgentFunction
from mail.net import SwarmRegistry
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

logger = logging.getLogger("mail.api")

ActionLike = TypeVar("ActionLike", bound=Callable[..., Awaitable[str] | str])


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
        exclude_tools: list[str] | None = None,
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
        self.exclude_tools = list(exclude_tools or [])
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
        exclude_tools: list[str] | None = None,
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
        self.exclude_tools = list(exclude_tools or [])
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

        # Remove tool_format from agent_params if present - top-level is authoritative
        agent_params = dict(self.agent_params)
        if "tool_format" in agent_params:
            logger.warning(
                f"agent '{self.name}' has tool_format in agent_params; "
                f"ignoring in favor of top-level tool_format='{self.tool_format}'"
            )
            agent_params.pop("tool_format")

        full_params = {
            **self._top_level_params(combined_exclude),
            **agent_params,
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


def _json_schema_to_python_type(
    schema: dict[str, Any],
    model_name_prefix: str = "Nested",
    _depth: int = 0,
) -> Any:
    """
    Recursively convert a JSON schema type definition to a Python type annotation.
    """
    schema_type = schema.get("type")

    if schema_type == "string":
        return str
    elif schema_type == "integer":
        return int
    elif schema_type == "number":
        return float
    elif schema_type == "boolean":
        return bool
    elif schema_type == "null":
        return type(None)
    elif schema_type == "array":
        items_schema = schema.get("items", {})
        if not items_schema:
            return list[Any]
        item_type = _json_schema_to_python_type(
            items_schema,
            f"{model_name_prefix}Item",
            _depth + 1,
        )
        return list[item_type]  # type: ignore[valid-type]
    elif schema_type == "object":
        properties = schema.get("properties")
        if properties:
            # Create a nested Pydantic model for structured objects
            return _json_schema_to_pydantic_model(
                f"{model_name_prefix}_{_depth}",
                schema,
            )
        else:
            # Generic dict - check additionalProperties for value type
            additional = schema.get("additionalProperties", {})
            if isinstance(additional, dict) and additional:
                value_type = _json_schema_to_python_type(
                    additional,
                    f"{model_name_prefix}Value",
                    _depth + 1,
                )
                return dict[str, value_type]  # type: ignore[valid-type]
            else:
                return dict[str, Any]
    elif schema_type is None:
        # Handle anyOf, oneOf, allOf
        any_of = schema.get("anyOf") or schema.get("oneOf")
        if any_of:
            types = [
                _json_schema_to_python_type(sub_schema, model_name_prefix, _depth + 1)
                for sub_schema in any_of
            ]
            if len(types) == 1:
                return types[0]
            # Create Union type using | operator
            result = types[0]
            for t in types[1:]:
                result = result | t
            return result
        all_of = schema.get("allOf")
        if all_of and len(all_of) == 1:
            return _json_schema_to_python_type(all_of[0], model_name_prefix, _depth + 1)
        return Any
    else:
        raise ValueError(f"unsupported JSON schema type: {schema_type}")


def _json_schema_to_pydantic_model(
    model_name: str,
    schema: dict[str, Any],
) -> type[BaseModel]:
    """
    Convert a JSON schema object definition to a Pydantic model.
    """
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_definitions: dict[str, tuple[Any, Any]] = {}

    for field_name, field_schema in properties.items():
        python_type = _json_schema_to_python_type(
            field_schema,
            f"{model_name}_{field_name}",
        )

        description = field_schema.get("description")
        default_value = field_schema.get("default", ...)

        is_required = field_name in required

        if not is_required and default_value is ...:
            # Optional field with no default - make it Optional with None default
            python_type = python_type | None
            default_value = None

        if description:
            field_info = Field(default=default_value, description=description)
        elif default_value is not ...:
            field_info = Field(default=default_value)
        else:
            field_info = Field()

        field_definitions[field_name] = (python_type, field_info)

    return create_model(model_name, **field_definitions)  # type: ignore[call-overload]


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
        resolved_function: Any
        if isinstance(function, str):
            resolved_function = read_python_string(function)
        else:
            resolved_function = function

        if isinstance(resolved_function, MAILAction):
            return resolved_function.function
        if not callable(resolved_function):
            raise TypeError(
                f"action function must be callable, got {type(resolved_function)}"
            )
        return resolved_function  # type: ignore[return-value]

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
            return _json_schema_to_pydantic_model(self.name, self.parameters)
        else:

            class MAILActionBaseModel(BaseModel):
                name: str = Field(description=self.name)
                description: str = Field(description=self.description)
                parameters: dict[str, Any] = Field()
                function: str = Field(description=str(self.function))

            return MAILActionBaseModel


def action(
    *,
    name: str | None = None,
    description: str | None = None,
    model: type[BaseModel] | None = None,
    parameters: dict[str, Any] | None = None,
    style: Literal["completions", "responses"] = "responses",
) -> Callable[[ActionLike], MAILAction]:
    """
    Decorator that converts a Python callable into a MAILAction.
    """

    if model is not None and not issubclass(model, BaseModel):
        msg = f"model must be a subclass of BaseModel, got {model}"
        raise TypeError(msg)

    def decorator(func: ActionLike) -> MAILAction:
        action_name = name or func.__name__
        docstring = description or inspect.getdoc(func) or ""
        clean_description = inspect.cleandoc(docstring)
        if len(clean_description) < 1:
            raise ValueError(
                f"Action '{action_name}' is missing a description. Provide one via "
                "`description=` or add a docstring."
            )

        signature = inspect.signature(func)
        if len(signature.parameters) != 1:
            raise TypeError(
                f"Action '{action_name}' must accept exactly one argument matching the "
                "tool payload."
            )

        resolved_model = model
        if resolved_model is None:
            type_hints = get_type_hints(func)
            first_param_name = next(iter(signature.parameters))
            candidate = type_hints.get(first_param_name)
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                resolved_model = candidate

        if resolved_model and parameters:
            raise ValueError(
                f"Action '{action_name}' cannot specify both model= and parameters=."
            )

        if resolved_model:
            tool_definition = pydantic_model_to_tool(
                resolved_model,
                name=action_name,
                description=clean_description,
                style=style,
            )
            action_parameters = tool_definition["parameters"]
        elif parameters:
            action_parameters = parameters
        else:
            raise ValueError(
                f"Action '{action_name}' must provide either a model= or parameters=."
            )

        @wraps(func)
        async def runner(payload: dict[str, Any]) -> str:
            if resolved_model is not None:
                parsed_payload = resolved_model.model_validate(payload)
            else:
                parsed_payload = payload  # type: ignore

            result = func(parsed_payload)
            if inspect.isawaitable(result):
                result = await result

            if not isinstance(result, str):
                raise TypeError(
                    f"Action '{action_name}' returned {type(result)}, expected str."
                )

            return result

        mail_action = MAILAction(
            name=action_name,
            description=clean_description,
            parameters=action_parameters,
            function=runner,
        )
        mail_action.callback = func  # type: ignore[attr-defined]
        mail_action.parameters_model = resolved_model  # type: ignore[attr-defined]
        return mail_action

    return decorator


class MAILSwarm:
    """
    Swarm instance class exposed via the MAIL API.
    """

    def __init__(
        self,
        name: str,
        version: str,
        agents: list[MAILAgent],
        actions: list[MAILAction],
        entrypoint: str,
        user_id: str = "default",
        user_role: Literal["admin", "agent", "user"] = "user",
        swarm_registry: SwarmRegistry | None = None,
        enable_interswarm: bool = False,
        breakpoint_tools: list[str] = [],
        exclude_tools: list[str] = [],
        task_message_limit: int | None = None,
        description: str = "",
        keywords: list[str] = [],
        enable_db_agent_histories: bool = False,
    ) -> None:
        self.name = name
        self.version = version
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.user_id = user_id
        self.swarm_registry = swarm_registry
        self.user_role = user_role
        self.enable_interswarm = enable_interswarm
        self.breakpoint_tools = breakpoint_tools
        self.exclude_tools = exclude_tools
        self.task_message_limit = task_message_limit
        self.description = description
        self.keywords = keywords
        self.adjacency_matrix, self.agent_names = self._build_adjacency_matrix()
        self.supervisors = [agent for agent in agents if agent.can_complete_tasks]
        self._agent_cores = {agent.name: agent.to_core() for agent in agents}
        self._runtime = MAILRuntime(
            agents=self._agent_cores,
            actions={action.name: action.to_core() for action in actions},
            user_id=user_id,
            user_role=user_role,
            swarm_name=name,
            swarm_registry=swarm_registry,
            enable_interswarm=enable_interswarm,
            entrypoint=entrypoint,
            breakpoint_tools=breakpoint_tools,
            exclude_tools=exclude_tools,
            enable_db_agent_histories=enable_db_agent_histories,
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
            subject=subject,
            body=body,
            targets=[entrypoint],
            sender_type=self.user_role,
            type=msg_type,
            task_id=task_id,
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
            subject=subject,
            body=body,
            targets=[entrypoint],
            sender_type=self.user_role,
            type=msg_type,
            task_id=task_id,
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
            subject=subject,
            body=body,
            targets=[entrypoint],
            sender_type=self.user_role,
            type=msg_type,
            task_id=task_id,
        )
        task_id = message["message"]["task_id"]
        if not resume_from == "breakpoint_tool_call":
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
        sender_type: Literal["admin", "agent", "user"] = "user",
        type: Literal["request", "response", "broadcast", "interrupt"] = "request",
        task_id: str | None = None,
    ) -> MAILMessage:
        """
        Build a MAIL message.
        """
        match sender_type:
            case "admin":
                sender = create_admin_address(self.user_id)
            case "agent":
                sender = create_agent_address(self.user_id)
            case "user":
                sender = create_user_address(self.user_id)
            case _:
                raise ValueError(f"invalid sender type: {sender_type}")
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
                        sender=sender,
                        recipient=create_agent_address(target),
                        subject=subject,
                        body=body,
                        sender_swarm=self.name,
                        recipient_swarm=self.name,
                        routing_info={},
                    ),
                    msg_type="request",
                )
            case "broadcast":
                return MAILMessage(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                    message=MAILBroadcast(
                        task_id=task_id or str(uuid.uuid4()),
                        broadcast_id=str(uuid.uuid4()),
                        sender=sender,
                        recipients=[create_agent_address(target) for target in targets],
                        subject=subject,
                        body=body,
                        sender_swarm=None,
                        recipient_swarms=None,
                        routing_info={},
                    ),
                    msg_type="broadcast",
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

    async def load_agent_histories_from_db(self) -> None:
        """
        Load existing agent histories from the database.
        Only has effect when enable_db_agent_histories is True.
        """
        await self._runtime.load_agent_histories_from_db()

    async def load_tasks_from_db(self) -> None:
        """
        Load existing tasks from the database.
        Only has effect when enable_db_agent_histories is True.
        """
        await self._runtime.load_tasks_from_db()

    async def run_continuous(
        self,
        max_steps: int | None = None,
        action_override: ActionOverrideFunction | None = None,
        mode: Literal["continuous", "manual"] = "continuous",
    ) -> None:
        """
        Run the MAILSwarm in continuous mode.
        """
        await self._runtime.run_continuous(max_steps, action_override, mode)

    async def manual_step(
        self,
        task_id: str,
        target: str,
        response_targets: list[str] | None = None,
        response_type: Literal["broadcast", "response", "request"] = "broadcast",
        payload: str | None = None,
        dynamic_ctx_ratio: float = 0.0,
        _llm: str | None = None,
        _system: str | None = None,
    ) -> MAILMessage:
        """
        Manually step a target agent.
        """
        return await self._runtime._manual_step(
            task_id=task_id,
            target=target,
            response_targets=response_targets,
            response_type=response_type,
            payload=payload,
            dynamic_ctx_ratio=dynamic_ctx_ratio,
            _llm=_llm,
            _system=_system,
        )

    async def await_queue_empty(self) -> None:
        """
        Await for the message queue to be empty.
        """
        while not self._runtime.message_queue.empty():
            await asyncio.sleep(0.1)

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

    async def submit_message_nowait(
        self,
        message: MAILMessage,
        **kwargs: Any,
    ) -> None:
        """
        Submit a fully-formed MAILMessage to the swarm and do not wait for the response.
        """
        await self._runtime.submit(message)

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

    def get_pending_requests(self) -> dict[str, asyncio.Future[MAILMessage]]:
        """
        Get the pending requests for the swarm.
        """
        return self._runtime.pending_requests

    async def receive_interswarm_message(
        self,
        message: MAILInterswarmMessage,
        direction: Literal["forward", "back"] = "forward",
    ) -> None:
        """
        Receive an interswarm message from a remote swarm.
        """
        router = self._runtime.interswarm_router
        if router is None:
            raise ValueError("interswarm router not available")

        try:
            if direction == "forward":
                await router.receive_interswarm_message_forward(message)
            elif direction == "back":
                await router.receive_interswarm_message_back(message)
            else:
                raise ValueError(f"invalid direction: {direction}")
        except Exception as e:
            raise ValueError(f"error routing interswarm message: {e}")

    async def send_interswarm_message(
        self,
        message: MAILInterswarmMessage,
        direction: Literal["forward", "back"] = "forward",
    ) -> None:
        """
        Send an interswarm message to a remote swarm.
        """
        router = self._runtime.interswarm_router
        if router is None:
            raise ValueError("interswarm router not available")

        try:
            if direction == "forward":
                await router.send_interswarm_message_forward(message)
            elif direction == "back":
                await router.send_interswarm_message_back(message)
            else:
                raise ValueError(f"invalid direction: {direction}")
        except Exception as e:
            raise ValueError(f"error sending interswarm message: {e}")

    async def post_interswarm_user_message(
        self,
        message: MAILInterswarmMessage,
    ) -> MAILMessage:
        """
        Post a message (from an admin or user) to a remote swarm.
        """
        router = self._runtime.interswarm_router
        if router is None:
            raise ValueError("interswarm router not available")

        try:
            result = await router.post_interswarm_user_message(message)
            return result
        except Exception as e:
            raise ValueError(f"error posting interswarm user message: {e}")

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
            version=self.version,
            agents=selected_agents,
            actions=actions,
            entrypoint=entrypoint_agent.name,
            enable_interswarm=self.enable_interswarm,
            enable_db_agent_histories=self._runtime.enable_db_agent_histories,
        )

    def get_response_message(self, task_id: str) -> MAILMessage | None:
        """
        Get the response message for a given task ID. Mostly used after streaming response events.
        """
        return self._runtime.get_response_message(task_id)

    def get_events(self, task_id: str) -> list[ServerSentEvent]:
        """
        Get the events for a given task ID. Mostly used after streaming response events.
        """
        return self._runtime.get_events_by_task_id(task_id)

    def get_all_tasks(self) -> dict[str, MAILTask]:
        """
        Get all tasks for the swarm.
        """
        return self._runtime.mail_tasks

    def get_task_by_id(self, task_id: str) -> MAILTask | None:
        """
        Get a task by ID.
        """
        return self._runtime.mail_tasks.get(task_id)


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
        version: str,
        agents: list[MAILAgentTemplate],
        actions: list[MAILAction],
        entrypoint: str,
        enable_interswarm: bool = False,
        breakpoint_tools: list[str] = [],
        exclude_tools: list[str] = [],
        task_message_limit: int | None = None,
        description: str = "",
        keywords: list[str] = [],
        public: bool = False,
        enable_db_agent_histories: bool = False,
    ) -> None:
        self.name = name
        self.version = version
        self.agents = agents
        self.actions = actions
        self.entrypoint = entrypoint
        self.enable_interswarm = enable_interswarm
        self.breakpoint_tools = breakpoint_tools
        self.exclude_tools = exclude_tools
        self.task_message_limit = task_message_limit
        self.description = description
        self.keywords = keywords
        self.public = public
        self.enable_db_agent_histories = enable_db_agent_histories
        self.adjacency_matrix, self.agent_names = self._build_adjacency_matrix()
        self.supervisors = [agent for agent in agents if agent.can_complete_tasks]
        self._validate()

    def _log_prelude(self) -> str:
        """
        Get the log prelude for the swarm template.
        """
        return f"[[green]{self.name}[/green] (template)]"

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
        user_role: Literal["admin", "agent", "user"] = "user",
        base_url: str = "http://localhost:8000",
        registry_file: str | None = None,
    ) -> MAILSwarm:
        """
        Instantiate a MAILSwarm from a MAILSwarmTemplate.
        """
        if self.enable_interswarm:
            swarm_registry = SwarmRegistry(
                self.name,
                base_url,
                registry_file,
                local_swarm_description=self.description,
                local_swarm_keywords=self.keywords,
                local_swarm_public=self.public,
            )
        else:
            swarm_registry = None

        agents = [
            agent.instantiate(
                instance_params, additional_exclude_tools=self.exclude_tools
            )
            for agent in self.agents
        ]

        for agent in agents:
            if isinstance(agent.function, MAILAgentFunction):
                function = agent.function
                if hasattr(function, "supervisor_fn"):
                    function = function.supervisor_fn  # type: ignore
                if hasattr(function, "action_agent_fn"):
                    function = function.action_agent_fn  # type: ignore
                logger.debug(
                    f"{self._log_prelude()} updating system prompt for agent '{agent.name}'"
                )
                delimiter = (
                    "Here are details about the agents you can communicate with:"
                )
                prompt: str = function.system  # type: ignore
                if delimiter in prompt:
                    lines = prompt.splitlines()
                    result_lines = []
                    for line in lines:
                        if delimiter in line:
                            break
                        result_lines.append(line)
                    prompt = "\n".join(result_lines)
                    prompt += f"\n\n{delimiter}\n\n"
                else:
                    prompt += f"\n\n{delimiter}\n\n"
                targets_as_agents = [a for a in agents if a.name in agent.comm_targets]
                for t in targets_as_agents:
                    prompt += f"Name: {t.name}\n"
                    prompt += "Capabilities:\n"
                    fn = t.function
                    logger.debug(
                        f"{self._log_prelude()} found target agent with fn of type '{type(fn)}'"
                    )
                    if isinstance(fn, MAILAgentFunction):
                        logger.debug("found target agent with MAILAgentFunction")
                        web_search = any(t["type"] == "web_search" for t in fn.tools)
                        code_interpreter = any(
                            t["type"] == "code_interpreter" for t in fn.tools
                        )
                        if web_search and code_interpreter:
                            prompt += "- This agent can search the web\n- This agent can execute code. The code it writes cannot access the internet."
                        if web_search and not code_interpreter:
                            prompt += "- This agent can search the web\n- This agent cannot execute code"
                        if not web_search and code_interpreter:
                            prompt += "- This agent can execute code. The code it writes cannot access the internet.\n- This agent cannot search the web"
                        if not web_search and not code_interpreter:
                            prompt += "- This agent does not have access to tools, the internet, real-time data, etc."
                    else:
                        prompt += "- This agent does not have access to tools, the internet, real-time data, etc."
                    prompt += "\n\n"
                prompt.strip()
                logger.debug(
                    f"{self._log_prelude()} updated system prompt for agent '{agent.name}' to '{prompt[:25]}...'"
                )
                function.system = prompt  # type: ignore

        return MAILSwarm(
            name=self.name,
            version=self.version,
            agents=agents,
            actions=self.actions,
            entrypoint=self.entrypoint,
            user_id=user_id,
            user_role=user_role,
            swarm_registry=swarm_registry,
            enable_interswarm=self.enable_interswarm,
            breakpoint_tools=self.breakpoint_tools,
            exclude_tools=self.exclude_tools,
            task_message_limit=self.task_message_limit,
            description=self.description,
            keywords=self.keywords,
            enable_db_agent_histories=self.enable_db_agent_histories,
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
            version=self.version,
            agents=selected_agents,
            actions=actions,
            entrypoint=entrypoint_agent.name,
            enable_interswarm=self.enable_interswarm,
            breakpoint_tools=self.breakpoint_tools,
            exclude_tools=self.exclude_tools,
            enable_db_agent_histories=self.enable_db_agent_histories,
        )

    @staticmethod
    def from_swarms_json(
        swarm_data: SwarmsJSONSwarm, task_message_limit: int | None = None
    ) -> "MAILSwarmTemplate":
        """
        Create a `MAILSwarmTemplate` from a pre-parsed `SwarmsJSONSwarm` definition.
        """
        inline_actions = [
            MAILAction.from_swarms_json(action) for action in swarm_data["actions"]
        ]
        imported_actions: list[MAILAction] = []
        for import_path in swarm_data.get("action_imports", []):
            resolved = read_python_string(import_path)
            if not isinstance(resolved, MAILAction):
                raise TypeError(
                    f"action import '{import_path}' in swarm '{swarm_data['name']}' did not resolve to a MAILAction"
                )
            imported_actions.append(resolved)

        combined_actions: dict[str, MAILAction] = {}
        for action in imported_actions + inline_actions:
            existing = combined_actions.get(action.name)
            if existing and existing is not action:
                raise ValueError(
                    f"duplicate action definition for '{action.name}' in swarm '{swarm_data['name']}'"
                )
            combined_actions[action.name] = action

        actions = list(combined_actions.values())
        actions_by_name = {action.name: action for action in actions}
        agents = [
            MAILAgentTemplate.from_swarms_json(agent, actions_by_name)
            for agent in swarm_data["agents"]
        ]

        return MAILSwarmTemplate(
            name=swarm_data["name"],
            version=swarm_data["version"],
            agents=agents,
            actions=actions,
            entrypoint=swarm_data["entrypoint"],
            enable_interswarm=swarm_data["enable_interswarm"],
            breakpoint_tools=swarm_data["breakpoint_tools"],
            exclude_tools=swarm_data["exclude_tools"],
            task_message_limit=task_message_limit,
            description=swarm_data.get("description", ""),
            keywords=swarm_data.get("keywords", []),
            public=swarm_data.get("public", False),
            enable_db_agent_histories=swarm_data.get(
                "enable_db_agent_histories", False
            ),
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

    def start_server(
        self,
        port: int = 8000,
        host: str = "0.0.0.0",
        launch_ui: bool = True,
        ui_port: int = 3000,
        ui_path: str | None = None,
        open_browser: bool = True,
        server_url: str | None = None,
    ) -> None:
        """Start a MAIL server with this swarm template.

        Blocks until Ctrl+C. Runs in single-process mode only.
        Debug mode is always enabled for /ui/message endpoint.

        Args:
            port: Server port (default 8000)
            host: Server host (default 0.0.0.0)
            launch_ui: Start Next.js UI dev server (default True)
            ui_port: UI dev server port (default 3000)
            ui_path: Path to UI directory (auto-detected if None)
            open_browser: Open browser to UI URL on startup (default True)
            server_url: URL the UI uses to connect to server (default: http://localhost:{port})

        Raises:
            ValueError: If template validation fails
            FileNotFoundError: If UI directory not found or node_modules missing
            RuntimeError: If UI process fails to start
            OSError: If port is already in use
        """
        import os
        import socket
        import subprocess
        import time
        import webbrowser

        from mail.server import run_server_with_template

        # Validate template first (already validated in __init__, but re-check)
        self._validate()

        # Resolve UI path
        if ui_path is None:
            package_dir = os.path.dirname(os.path.abspath(__file__))
            ui_path = os.path.normpath(os.path.join(package_dir, "..", "..", "ui"))

        # Compute server URL for UI to connect to
        # Smart default: localhost for wildcard bindings, else use the actual host
        if server_url is None:
            # Wildcard addresses (IPv4 0.0.0.0, IPv6 ::) and localhost variants -> localhost
            if host in ("0.0.0.0", "127.0.0.1", "localhost", "::", "::1"):
                server_url = f"http://localhost:{port}"
            else:
                server_url = f"http://{host}:{port}"

        ui_proc = None

        if launch_ui:
            # Validate UI directory exists
            if not os.path.isdir(ui_path):
                raise FileNotFoundError(
                    f"UI directory not found at {ui_path}. "
                    f"Set ui_path parameter or use launch_ui=False."
                )

            # Check node_modules exists
            node_modules = os.path.join(ui_path, "node_modules")
            if not os.path.isdir(node_modules):
                raise FileNotFoundError(
                    f"node_modules not found in {ui_path}. "
                    f"Run 'pnpm install' in the UI directory first."
                )

            # Check if UI port is available before launching
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", ui_port)) == 0:
                    raise OSError(f"UI port {ui_port} is already in use. Try a different ui_port.")

            # Print startup banner
            print(f"\n{'='*60}")
            print(f"  MAIL Swarm Viewer")
            print(f"  Swarm: {self.name}")
            print(f"  Agents: {', '.join(self.agent_names)}")
            print(f"{'='*60}")
            print(f"  Server: http://{host}:{port}")
            print(f"  UI:     http://localhost:{ui_port}")
            print(f"{'='*60}")
            print(f"  Press Ctrl+C to stop\n")

            # Set up environment for UI to connect to server
            ui_env = os.environ.copy()
            ui_env["NEXT_PUBLIC_MAIL_SERVER_URL"] = server_url

            # Start UI dev server in background
            # Note: stdout/stderr suppressed for cleaner output. If UI fails to start,
            # the error message directs users to run pnpm dev manually.
            ui_proc = subprocess.Popen(
                ["pnpm", "dev", "--port", str(ui_port)],
                cwd=ui_path,
                env=ui_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Poll to verify UI process started successfully
            time.sleep(2)
            if ui_proc.poll() is not None:
                # Process exited - UI failed to start
                raise RuntimeError(
                    f"UI dev server failed to start (exit code {ui_proc.returncode}).\n"
                    f"To see the actual error, run manually:\n"
                    f"  cd {ui_path} && pnpm dev --port {ui_port}"
                )

            # Open browser (with WSL2 support)
            if open_browser:
                url = f"http://localhost:{ui_port}"
                # Detect WSL2 and use Windows browser
                # os.uname() doesn't exist on native Windows, so guard with try/except
                is_wsl = False
                try:
                    is_wsl = "microsoft" in os.uname().release.lower()
                except AttributeError:
                    pass  # Native Windows - os.uname() doesn't exist

                if is_wsl:
                    # WSL2: use cmd.exe to open Windows default browser
                    subprocess.Popen(
                        ["cmd.exe", "/c", "start", "", url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    webbrowser.open(url)
        else:
            # Server-only banner
            print(f"\n{'='*60}")
            print(f"  MAIL Server")
            print(f"  Swarm: {self.name}")
            print(f"  Agents: {', '.join(self.agent_names)}")
            print(f"{'='*60}")
            print(f"  Server: http://{host}:{port}")
            print(f"{'='*60}")
            print(f"  Press Ctrl+C to stop\n")

        try:
            run_server_with_template(
                template=self,
                port=port,
                host=host,
                task_message_limit=None,
            )
        except OSError as e:
            if "Address already in use" in str(e) or getattr(e, 'errno', None) == 98:
                raise OSError(f"Port {port} is already in use. Try a different port.") from e
            raise
        finally:
            # Graceful shutdown of UI process
            if ui_proc is not None:
                ui_proc.terminate()
                try:
                    ui_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    ui_proc.kill()
