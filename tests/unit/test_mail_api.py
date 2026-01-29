# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
from collections.abc import AsyncGenerator
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ValidationError

from mail.api import MAILAction, MAILAgent, MAILAgentTemplate, MAILSwarmTemplate, action
from mail.swarms_json.utils import build_swarm_from_swarms_json
from tests.conftest import TEST_SYSTEM_PROMPT, make_stub_agent


class FakeMAILRuntime:
    """
    Lightweight stub for mail.core.MAILRuntime used by MAILSwarm tests.
    """

    def __init__(
        self,
        agents: Any,
        actions: Any,
        user_id: str,
        user_role: str,
        swarm_name: str,
        entrypoint: str,
        swarm_registry: Any | None = None,  # noqa: ARG002
        enable_interswarm: bool | None = None,  # noqa: ARG002
        breakpoint_tools: list[str] | None = None,  # noqa: ARG002
        exclude_tools: list[str] | None = None,  # noqa: ARG002
        enable_db_agent_histories: bool = False,  # noqa: ARG002
    ) -> None:
        self.agents = agents
        self.actions = actions
        self.user_id = user_id
        self.user_role = user_role
        self.swarm_name = swarm_name
        self.entrypoint = entrypoint
        self.submitted: list[dict[str, Any]] = []
        self._events: dict[str, list[Any]] = {}
        self.breakpoint_tools = breakpoint_tools
        self.exclude_tools = exclude_tools

    @pytest.mark.asyncio
    async def submit_and_wait(
        self,
        message: dict[str, Any],
        _timeout: float = 3600.0,
        _resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Replacement for `MAILRuntime.submit_and_wait`.
        """
        self.submitted.append(message)
        task_id = message["message"]["task_id"]
        self._events.setdefault(task_id, []).append({"event": "debug", "data": "ok"})
        # Minimal response echoing back task_id and flipping sender/recipient
        return {
            "id": "resp-1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "message": {
                "task_id": task_id,
                "request_id": message["message"]["request_id"],
                "sender": message["message"]["recipient"],
                "recipient": message["message"]["sender"],
                "subject": "ok",
                "body": "done",
                "sender_swarm": self.swarm_name,
                "recipient_swarm": self.swarm_name,
                "routing_info": {},
            },
            "msg_type": "response",
        }

    def get_events_by_task_id(self, task_id: str) -> list[Any]:
        """
        Replacement for `MAILRuntime.get_events_by_task_id`.
        """
        return self._events.get(task_id, [])

    @pytest.mark.asyncio
    async def submit_and_stream(
        self,
        _message: dict[str, Any],
        _timeout: float = 3600.0,
        _resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Replacement for `MAILRuntime.submit_and_stream`.
        """

        async def _stream() -> AsyncGenerator[dict[str, Any], None]:
            yield {"event": "message", "data": "chunk1"}
            yield {"event": "message", "data": "chunk2"}

        return _stream()


@pytest.fixture(autouse=True)
def patch_mail_in_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Patch the `MAILRuntime` used inside `mail.api` to avoid heavy runtime behavior.
    """
    # Patch the MAILRuntime used inside mail.api to avoid heavy runtime behavior
    import mail.api as api

    monkeypatch.setattr(api, "MAILRuntime", FakeMAILRuntime)


def test_from_swarm_json_valid_creates_swarm() -> None:
    """
    Test that `MAILSwarmTemplate.from_swarm_json` works as expected.
    """
    data = {
        "name": "myswarm",
        "version": "1.3.2",
        "description": "demo swarm",
        "keywords": ["demo", "mail"],
        "public": True,
        "agents": [
            {
                "name": "supervisor",
                "factory": "tests.conftest:make_stub_agent",
                "comm_targets": ["analyst"],
                "can_complete_tasks": True,
                "actions": [],
                "enable_entrypoint": True,
                "agent_params": {},
            },
            {
                "name": "analyst",
                "factory": "tests.conftest:make_stub_agent",
                "comm_targets": ["supervisor"],
                "actions": [],
                "agent_params": {},
            },
        ],
        "actions": [],
        "entrypoint": "supervisor",
        "breakpoint_tools": [],
    }

    tmpl = MAILSwarmTemplate.from_swarm_json(json.dumps(data))
    swarm = tmpl.instantiate(instance_params={}, user_id="u-1")
    assert swarm.name == "myswarm"
    assert swarm.entrypoint == "supervisor"
    # Ensure runtime was created with our stub
    assert isinstance(swarm._runtime, FakeMAILRuntime)
    assert swarm._runtime.user_id == "u-1"
    assert swarm._runtime.swarm_name == "myswarm"
    assert tmpl.description == "demo swarm"
    assert tmpl.keywords == ["demo", "mail"]
    assert tmpl.public is True


def test_swarm_level_exclude_tools_union() -> None:
    """
    Swarm-level tool exclusions should be merged with agent-level exclusions.
    """
    captured: dict[str, list[str]] = {}

    def stub_factory(**kwargs: Any):
        captured["exclude_tools"] = kwargs["exclude_tools"]

        async def agent(_history: list[dict[str, Any]], _tool_choice: str = "required"):
            return None, []

        return agent

    agent_template = MAILAgentTemplate(
        name="supervisor",
        factory=stub_factory,
        comm_targets=["supervisor"],
        actions=[],
        agent_params={},
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
        tool_format="responses",
        exclude_tools=["send_request"],
    )

    swarm_template = MAILSwarmTemplate(
        name="myswarm",
        version="1.3.2",
        agents=[agent_template],
        actions=[],
        entrypoint="supervisor",
        enable_interswarm=False,
        breakpoint_tools=[],
        exclude_tools=["send_response"],
    )

    swarm = swarm_template.instantiate(instance_params={}, user_id="tester")

    assert "exclude_tools" in captured
    assert set(captured["exclude_tools"]) == {"send_request", "send_response"}
    assert set(swarm.agents[0].exclude_tools) == {"send_request", "send_response"}


def test_agent_params_prefixed_python_strings_resolved() -> None:
    """
    Ensure agent_params values with the python prefix are resolved.
    """
    data = {
        "name": "myswarm",
        "version": "1.3.2",
        "agents": [
            {
                "name": "supervisor",
                "factory": "tests.conftest:make_stub_agent",
                "comm_targets": ["supervisor"],
                "can_complete_tasks": True,
                "actions": [],
                "enable_entrypoint": True,
                "agent_params": {
                    "system": "python::tests.conftest:TEST_SYSTEM_PROMPT",
                },
            },
        ],
        "actions": [],
        "entrypoint": "supervisor",
        "breakpoint_tools": [],
    }

    tmpl = MAILSwarmTemplate.from_swarm_json(json.dumps(data))
    agent = tmpl.agents[0]
    assert agent.agent_params["system"] == TEST_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "missing",
    ["name", "agents", "entrypoint"],
)
def test_from_swarm_json_missing_required_field_raises(missing: str) -> None:
    """
    Test that `MAILSwarmTemplate.from_swarm_json` raises an error if a required field is missing.
    """
    from mail import MAILSwarmTemplate

    base = {
        "name": "x",
        "version": "1.3.2",
        "agents": [],
        "actions": [],
        "entrypoint": "supervisor",
        "breakpoint_tools": [],
    }
    bad = base.copy()
    bad.pop(missing)

    with pytest.raises(ValueError) as exc:
        MAILSwarmTemplate.from_swarm_json(json.dumps(bad))
    assert "must contain" in str(exc.value)


def test_from_swarm_json_wrong_types_raise() -> None:
    """
    Test that `MAILSwarmTemplate.from_swarm_json` raises an error if a field is the wrong type.
    """
    from mail import MAILSwarmTemplate

    bad = {
        "name": 123,
        "version": "1.3.2",
        "agents": {},
        "actions": {},
        "entrypoint": 999,
        "breakpoint_tools": "supervisor",
    }

    with pytest.raises(ValueError) as exc:
        MAILSwarmTemplate.from_swarm_json(json.dumps(bad))
    # Message should note type mismatch
    assert "must be a" in str(exc.value)


def test_from_swarm_json_file_selects_named_swarm(tmp_path: Any) -> None:
    """
    Test that `MAILSwarmTemplate.from_swarm_json_file` works as expected.
    """
    from mail import MAILSwarmTemplate

    contents = [
        {
            "name": "other",
            "version": "1.3.2",
            "agents": [],
            "actions": [],
            "entrypoint": "s",
        },
        {
            "name": "target",
            "version": "1.3.2",
            "agents": [
                {
                    "name": "supervisor",
                    "factory": "tests.conftest:make_stub_agent",
                    "comm_targets": ["analyst"],
                    "actions": [],
                    "can_complete_tasks": True,
                    "enable_entrypoint": True,
                    "agent_params": {},
                },
                {
                    "name": "analyst",
                    "factory": "tests.conftest:make_stub_agent",
                    "comm_targets": ["supervisor"],
                    "actions": [],
                    "agent_params": {},
                },
            ],
            "actions": [],
            "entrypoint": "supervisor",
        },
    ]
    path = tmp_path / "swarms.json"
    path.write_text(json.dumps(contents))

    tmpl = MAILSwarmTemplate.from_swarm_json_file("target", str(path))
    assert tmpl.name == "target"


def test_mailagent_to_core_preserves_actions() -> None:
    """
    Ensure MAILAgent.to_core retains assigned action permissions.
    """

    async def fake_action(_: dict[str, Any]) -> str:
        return "ok"

    action = MAILAction(
        name="get_weather_forecast",
        description="Fetch weather forecast",
        parameters={"type": "object", "properties": {}},
        function=fake_action,
    )

    async def noop_agent(
        _messages: list[dict[str, Any]], _tool_choice: str
    ) -> tuple[str | None, list[Any]]:
        return None, []

    agent = MAILAgent(
        name="weather",
        factory="tests.conftest:make_stub_agent",
        actions=[action],
        function=noop_agent,  # type: ignore[arg-type]
        comm_targets=["supervisor"],
        agent_params={},
    )

    core = agent.to_core()

    assert core.can_access_action("get_weather_forecast")
    assert "get_weather_forecast" in core.actions


@pytest.mark.asyncio
async def test_post_message_uses_default_entrypoint_and_returns_events() -> None:
    """
    Test that `MAILSwarm.post_message` works as expected.
    """
    from mail import MAILSwarm

    swarm = MAILSwarm(
        name="myswarm",
        version="1.3.2",
        agents=[
            MAILAgent(
                name="supervisor",
                factory="tests.conftest:make_stub_agent",
                actions=[],
                function=make_stub_agent,  # type: ignore[arg-type]
                comm_targets=["analyst"],
                can_complete_tasks=True,
                enable_entrypoint=True,
                agent_params={},
            ),
            MAILAgent(
                name="analyst",
                factory="tests.conftest:make_stub_agent",
                actions=[],
                function=make_stub_agent,  # type: ignore[arg-type]
                comm_targets=["supervisor"],
                enable_entrypoint=False,
                agent_params={},
            ),
        ],
        actions=[],
        entrypoint="supervisor",
    )

    # Call without explicit entrypoint -> defaults to MAILSwarm.entrypoint
    resp, events = await swarm.post_message(
        subject="hello", body="world", show_events=True
    )

    assert resp["msg_type"] == "response"
    # Ensure the request was submitted targeting the default entrypoint
    submitted = swarm._runtime.submitted  # type: ignore[attr-defined]
    assert len(submitted) == 1
    target = submitted[0]["message"]["recipient"]
    assert isinstance(target, dict) and target.get("address") == "supervisor"
    assert isinstance(events, list) and len(events) >= 1


@pytest.mark.asyncio
async def test_post_message_stream_headers_and_type() -> None:
    """
    Test that `MAILSwarm.post_message_stream` works as expected.
    """
    from sse_starlette import EventSourceResponse

    from mail import MAILSwarm

    swarm = MAILSwarm(
        name="myswarm",
            version="1.3.2",
        agents=[
            MAILAgent(
                name="supervisor",
                factory="tests.conftest:make_stub_agent",
                actions=[],
                function=make_stub_agent,  # type: ignore[arg-type]
                comm_targets=["analyst"],
                can_complete_tasks=True,
                enable_entrypoint=True,
                agent_params={},
            ),
            MAILAgent(
                name="analyst",
                factory="tests.conftest:make_stub_agent",
                actions=[],
                function=make_stub_agent,  # type: ignore[arg-type]
                comm_targets=["supervisor"],
                enable_entrypoint=False,
                agent_params={},
            ),
        ],
        actions=[],
        entrypoint="supervisor",
    )

    stream_resp = await swarm.post_message_stream(subject="hello", body="world")
    assert isinstance(stream_resp, EventSourceResponse)
    for key in ("Cache-Control", "Connection", "X-Accel-Buffering"):
        assert key in stream_resp.headers


def test_build_message_request_validation() -> None:
    """
    Test that `MAILSwarm.build_message` works as expected.
    """
    from mail import MAILSwarm

    swarm = MAILSwarm(
        name="myswarm",
        version="1.3.2",
        agents=[
            MAILAgent(
                name="supervisor",
                factory="tests.conftest:make_stub_agent",
                actions=[],
                function=make_stub_agent,  # type: ignore[arg-type]
                comm_targets=["analyst"],
                can_complete_tasks=True,
                enable_entrypoint=True,
                agent_params={},
            ),
            MAILAgent(
                name="analyst",
                factory="tests.conftest:make_stub_agent",
                actions=[],
                function=make_stub_agent,  # type: ignore[arg-type]
                comm_targets=["supervisor"],
                enable_entrypoint=False,
                agent_params={},
            ),
        ],
        actions=[],
        entrypoint="supervisor",
    )

    # _build_message should require exactly one target for requests
    with pytest.raises(ValueError):
        swarm.build_message("subj", "body", ["a", "b"], type="request")


async def _stub_action(_: dict[str, Any]) -> str:
    return "ok"


EMPTY_PARAMETERS = {"type": "object", "properties": {}}


@action(
    name="decorated_for_string",
    description="Return ok.",
    parameters=EMPTY_PARAMETERS,
)
async def decorated_for_string(_: dict[str, Any]) -> str:
    return "ok"


def test_mailaction_to_pydantic_model_for_tools_enforces_types() -> None:
    """
    `MAILAction.to_pydantic_model(for_tools=True)` should enforce declared types.
    """
    action = MAILAction(
        name="demo",
        description="Demo action",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Subject"},
                "retries": {"type": "integer", "description": "Attempts"},
                "notify": {"type": "boolean", "description": "Flag"},
            },
        },
        function=_stub_action,
    )

    model_cls = action.to_pydantic_model(for_tools=True)
    payload = model_cls(subject="Plan", retries=2, notify=False)
    assert payload.subject == "Plan"  # type: ignore
    assert payload.retries == 2  # type: ignore
    assert payload.notify is False  # type: ignore

    with pytest.raises(ValidationError):
        model_cls(subject=123, retries="two", notify="nope")


def test_mailaction_to_pydantic_model_unsupported_type_raises() -> None:
    """
    Unsupported parameter types should raise a ValueError during conversion.
    """
    action = MAILAction(
        name="bad",
        description="Bad action",
        parameters={
            "type": "object",
            "properties": {
                "payload": {"type": "dummy", "description": "Unsupported"},
            },
        },
        function=_stub_action,
    )

    with pytest.raises(ValueError) as exc:
        action.to_pydantic_model(for_tools=True)
    assert "unsupported JSON schema type" in str(exc.value)


@pytest.mark.parametrize("missing", ["name", "description", "parameters", "function"])
def test_mailaction_from_swarm_json_missing_required_field(missing: str) -> None:
    """
    MAILAction.from_swarm_json should validate presence of required keys.
    """
    base = {
        "name": "act",
        "description": "desc",
        "parameters": {"type": "object", "properties": {}},
        "function": "tests.conftest:make_stub_agent",
    }
    bad = base.copy()
    bad.pop(missing)

    with pytest.raises(ValueError) as exc:
        MAILAction.from_swarm_json(json.dumps(bad))
    assert "must contain" in str(exc.value)


def test_mailaction_from_swarm_json_type_validation() -> None:
    """
    AILAction.from_swarm_json should reject incorrect types.
    """
    bad = {
        "name": 123,
        "description": "desc",
        "parameters": {"type": "object", "properties": {}},
        "function": "tests.conftest:make_stub_agent",
    }

    with pytest.raises(ValueError) as exc:
        MAILAction.from_swarm_json(json.dumps(bad))
    assert "must be a" in str(exc.value)


@pytest.mark.asyncio
async def test_action_decorator_builds_mail_action_from_model() -> None:
    """
    The decorator should wrap an async callable and enforce the supplied Pydantic model.
    """

    class Payload(BaseModel):
        location: str

    @action(model=Payload, description="Return the requested location.")
    async def locate(data: Payload) -> str:
        return data.location.upper()

    assert isinstance(locate, MAILAction)
    assert locate.name == "locate"
    assert locate.description == "Return the requested location."
    assert locate.parameters_model is Payload  # type: ignore[attr-defined]

    response = await locate.function({"location": "denver"})  # type: ignore[arg-type]
    assert response == "DENVER"
    assert locate.callback.__name__ == "locate"  # type: ignore[attr-defined]
    assert locate.parameters["properties"]["location"]["type"] == "string"


@pytest.mark.asyncio
async def test_action_decorator_infers_model_from_annotation() -> None:
    """
    When no model is provided, the decorator should infer it from a BaseModel annotation.
    """

    class ForecastInput(BaseModel):
        query: str

    @action(description="Return the forecast for the given query.")
    async def forecast(payload: ForecastInput) -> str:
        return f"forecast:{payload.query}"

    assert isinstance(forecast, MAILAction)
    assert forecast.parameters_model is ForecastInput  # type: ignore[attr-defined]
    result = await forecast.function({"query": "snow"})  # type: ignore[arg-type]
    assert result == "forecast:snow"


@pytest.mark.asyncio
async def test_mailaction_resolves_decorated_function_from_string() -> None:
    """
    MAILAction should load decorated actions when referenced via python strings.
    """
    action_from_string = MAILAction(
        name="via_string",
        description="Use decorated action.",
        parameters={"type": "object", "properties": {}},
        function="tests.unit.test_mail_api:decorated_for_string",
    )

    result = await action_from_string.function({})  # type: ignore[arg-type]
    assert result == "ok"


@pytest.mark.asyncio
async def test_action_decorator_supports_sync_functions_with_parameters() -> None:
    """
    Sync callables can be wrapped when a parameters schema is provided explicitly.
    """

    @action(
        name="ping",
        description="Return pong.",
        parameters={"type": "object", "properties": {}},
    )
    def ping(payload: dict[str, Any]) -> str:
        return "pong"

    assert isinstance(ping, MAILAction)
    result = await ping.function({})  # type: ignore[arg-type]
    assert result == "pong"
    assert ping.parameters["type"] == "object"


def test_action_decorator_missing_description_raises() -> None:
    """
    A description (or docstring) must be supplied for decorated actions.
    """

    class Empty(BaseModel):
        value: str

    with pytest.raises(ValueError):

        @action(model=Empty)
        async def undecorated(_: Empty) -> str:
            return "nope"


def test_swarm_template_action_imports_populate_actions() -> None:
    """
    Imported actions should be available to the swarm and its agents.
    """
    swarm_candidate = {
        "name": "imported",
        "version": "1.3.2",
        "entrypoint": "alpha",
        "agents": [
            {
                "name": "alpha",
                "factory": "tests.conftest:make_stub_agent",
                "comm_targets": [],
                "actions": ["decorated_for_string"],
                "agent_params": {},
                "enable_entrypoint": True,
                "enable_interswarm": False,
                "can_complete_tasks": True,
                "tool_format": "responses",
                "exclude_tools": [],
            }
        ],
        "actions": [],
        "action_imports": ["python::tests.unit.test_mail_api:decorated_for_string"],
        "enable_interswarm": False,
        "breakpoint_tools": [],
        "exclude_tools": [],
    }

    parsed_swarm = build_swarm_from_swarms_json(swarm_candidate)
    template = MAILSwarmTemplate.from_swarms_json(parsed_swarm)

    assert len(template.actions) == 1
    action = template.actions[0]
    assert action.name == decorated_for_string.name
    assert action.description == decorated_for_string.description
    assert template.agents[0].actions[0] is action


def test_swarm_template_action_imports_duplicate_names_raise() -> None:
    """
    Inline actions that collide with imported action names should raise an error.
    """
    swarm_candidate = {
        "name": "imported",
        "version": "1.3.2",
        "entrypoint": "alpha",
        "agents": [
            {
                "name": "alpha",
                "factory": "tests.conftest:make_stub_agent",
                "comm_targets": [],
                "actions": ["decorated_for_string"],
                "agent_params": {},
                "enable_entrypoint": True,
                "enable_interswarm": False,
                "can_complete_tasks": True,
                "tool_format": "responses",
                "exclude_tools": [],
            }
        ],
        "actions": [
            {
                "name": "decorated_for_string",
                "description": "Inline duplicate",
                "parameters": {"type": "object", "properties": {}},
                "function": "python::tests.unit.test_mail_api:decorated_for_string",
            }
        ],
        "action_imports": ["python::tests.unit.test_mail_api:decorated_for_string"],
        "enable_interswarm": False,
        "breakpoint_tools": [],
        "exclude_tools": [],
    }

    parsed_swarm = build_swarm_from_swarms_json(swarm_candidate)
    with pytest.raises(ValueError) as exc:
        MAILSwarmTemplate.from_swarms_json(parsed_swarm)
    assert "duplicate action definition" in str(exc.value)
