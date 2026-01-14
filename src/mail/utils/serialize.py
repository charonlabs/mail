from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

import ujson
from sse_starlette import ServerSentEvent

from mail.core.message import MAILMessage
from mail.utils.version import get_version

_REDACT_KEYS = {
    "id",
    "task_id",
    "request_id",
    "broadcast_id",
    "message_id",
    "event_id",
    "timestamp",
    "created_at",
    "updated_at",
    "sent_at",
    "received_at",
}


def dump_mail_result(
    result: MAILMessage,
    events: list[ServerSentEvent],
    verbose: bool = False,
) -> str:
    """
    For a completed MAIL task, create an LLM-friendly string dump of the result and events.
    """
    serialized_result = serialize_mail_value(result, exclude_keys=_REDACT_KEYS)
    if not verbose:
        return str(serialized_result["message"]["body"])

    serialized_events = []
    for event in events:
        serialized = _serialize_event(event, exclude_keys=_REDACT_KEYS)
        if serialized is not None:
            serialized_events.append(serialized)

    event_sections = _format_event_sections(serialized_events)
    result_section = str(serialized_result["message"]["body"])

    sections: list[str] = [
        "=== MAIL EVENTS ===",
        event_sections if event_sections else "(no events)",
        "=== FINAL ANSWER ===",
        result_section,
    ]
    return "\n".join(sections)


def serialize_mail_value(
    value: Any, *, exclude_keys: frozenset[str] | set[str] | None = None
) -> Any:
    """
    Convert MAIL runtime objects into JSON-friendly primitives.
    """
    exclude_keys = frozenset() if exclude_keys is None else frozenset(exclude_keys)

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {
            k: serialize_mail_value(v, exclude_keys=exclude_keys)
            for k, v in value.items()
            if k not in exclude_keys
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [serialize_mail_value(v, exclude_keys=exclude_keys) for v in value]
    if is_dataclass(value):
        return serialize_mail_value(asdict(value), exclude_keys=exclude_keys)  # type: ignore[arg-type]
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
        except TypeError:
            dumped = value.model_dump(mode="python")
        return serialize_mail_value(dumped, exclude_keys=exclude_keys)
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
        except TypeError:
            dumped = value.dict()
        return serialize_mail_value(dumped, exclude_keys=exclude_keys)
    if hasattr(value, "__dict__"):
        return {
            k: serialize_mail_value(v, exclude_keys=exclude_keys)
            for k, v in vars(value).items()
            if not k.startswith("_")
        }
    return str(value)


def _normalise_event_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return ujson.loads(payload)
        except ValueError:
            return payload
    return payload


def _serialize_event(
    event: ServerSentEvent, *, exclude_keys: frozenset[str] | set[str] | None
) -> dict[str, Any] | None:
    payload = _normalise_event_payload(event.data)
    if _should_skip_event(payload):
        return None
    event_type = _standardise_event_type(getattr(event, "event", None))

    description = ""
    if isinstance(payload, Mapping):
        description = str(dict(payload).get("description", ""))

    result = {
        "event": event_type,
        "description": description,
    }
    return result


def _standardise_event_type(event_name: Any) -> str:
    if not isinstance(event_name, str):
        return ""
    normalised = event_name.strip()
    normalised_key = normalised.casefold().replace(" ", "_")
    if normalised_key == "action_complete":
        return "action_output"
    return normalised


def _should_skip_event(payload: Any) -> bool:
    return _is_action_complete_broadcast(payload)


def _is_action_complete_broadcast(payload: Any) -> bool:
    """
    Check if the payload is an `action_complete_broadcast` message.
    """
    if not isinstance(payload, Mapping):
        return False
    description = payload.get("description")
    if not isinstance(description, str):
        return False
    if "<subject>::action_complete_broadcast::</subject>" in description:
        return True
    return False


def _format_event_sections(events: list[Any]) -> str:
    sections: list[str] = []
    for idx, event in enumerate(events, start=1):
        sections.append(f"--- Event {idx} ---\n{_format_json(event)}")
    return "\n\n".join(sections)


def _format_json(payload: Any) -> str:
    if isinstance(payload, str | int | float | bool) or payload is None:
        return str(payload)
    return ujson.dumps(payload, indent=2)


def extract_task_body(raw_result: Any, serialized_result: Any | None = None) -> Any:
    """
    Extract the body from a MAIL result.
    """
    for candidate in (raw_result, serialized_result):
        if candidate is None:
            continue
        if isinstance(candidate, Mapping):
            if "body" in candidate:
                return candidate["body"]
            message = candidate.get("message")
            if isinstance(message, Mapping) and "body" in message:
                return message["body"]
        if hasattr(candidate, "body"):
            body_attr = getattr(candidate, "body")
            if body_attr is not None:
                return body_attr
        if hasattr(candidate, "message"):
            message_obj = getattr(candidate, "message")
            if isinstance(message_obj, Mapping) and "body" in message_obj:
                return message_obj["body"]
            if hasattr(message_obj, "body"):
                body_attr = getattr(message_obj, "body")
                if body_attr is not None:
                    return body_attr
    return None


def export(swarms: list[Any]) -> str:
    """
    Export a `MAILSwarm` or `MAILSwarmTemplate` to a JSON string compatible
    with the client-side `Generation`/`Swarm` interfaces.
    """

    def _format_python_reference(reference: Any) -> str | None:
        if reference is None:
            return None
        if isinstance(reference, str):
            return reference
        if callable(reference):
            module = getattr(reference, "__module__", "")
            qualname = getattr(
                reference, "__qualname__", getattr(reference, "__name__", "")
            )
            if module and qualname:
                return f"python::{module}:{qualname}"
            if qualname:
                return qualname
        return None

    def _serialize_agent(agent: Any) -> dict[str, Any]:
        agent_dict: dict[str, Any] = {
            "name": getattr(agent, "name", ""),
            "comm_targets": list(getattr(agent, "comm_targets", [])),
            "enable_entrypoint": bool(getattr(agent, "enable_entrypoint", False)),
            "enable_interswarm": bool(getattr(agent, "enable_interswarm", False)),
            "can_complete_tasks": bool(getattr(agent, "can_complete_tasks", False)),
            "tool_format": getattr(agent, "tool_format", "responses"),
            "agent_params": serialize_mail_value(getattr(agent, "agent_params", {})),
        }

        factory_ref = _format_python_reference(getattr(agent, "factory", None))
        if factory_ref:
            agent_dict["factory"] = factory_ref

        actions = getattr(agent, "actions", [])
        if actions:
            agent_dict["actions"] = [
                getattr(action, "name", serialize_mail_value(action))
                for action in actions
            ]

        breakpoint_tools = getattr(agent, "breakpoint_tools", None)
        if breakpoint_tools:
            agent_dict["breakpoint_tools"] = list(breakpoint_tools)

        return agent_dict

    def _serialize_action(action: Any) -> dict[str, Any]:
        action_dict: dict[str, Any] = {
            "name": getattr(action, "name", ""),
            "description": getattr(action, "description", ""),
            "parameters": serialize_mail_value(getattr(action, "parameters", {})),
        }
        function_ref = _format_python_reference(getattr(action, "function", None))
        if function_ref:
            action_dict["function"] = function_ref
        return action_dict

    swarm_payloads: list[dict[str, Any]] = []
    for swarm in swarms:
        agent_payloads = [
            _serialize_agent(agent) for agent in getattr(swarm, "agents", [])
        ]
        action_payloads = [
            _serialize_action(action) for action in getattr(swarm, "actions", [])
        ]

        swarm_payload: dict[str, Any] = {
            "name": getattr(swarm, "name", ""),
            "version": get_version(),
            "entrypoint": getattr(swarm, "entrypoint", ""),
            "enable_interswarm": bool(getattr(swarm, "enable_interswarm", False)),
            "agents": agent_payloads,
        }

        breakpoint_tools = getattr(swarm, "breakpoint_tools", None)
        if breakpoint_tools is not None:
            swarm_payload["breakpoint_tools"] = list(breakpoint_tools)

        if action_payloads:
            swarm_payload["actions"] = action_payloads

        user_id = getattr(swarm, "user_id", None)
        if user_id is not None:
            swarm_payload["user_id"] = user_id

        swarm_payloads.append(swarm_payload)

    swarms_payload = {
        "swarms": swarm_payloads,
        "n": len(swarm_payloads),
    }

    return ujson.dumps(swarms_payload)
