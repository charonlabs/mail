from collections.abc import Awaitable, Callable
import datetime
from typing import Any, Optional
from uuid import uuid4

from litellm.utils import function_to_dict
from pydantic import BaseModel, Field

from .message import (
    MAILBroadcast,
    MAILInterrupt,
    MAILMessage,
    MAILRequest,
    MAILResponse,
    create_agent_address,
    create_system_address,
    create_user_address,
)

MAIL_TOOL_NAMES = [
    "send_request",
    "send_response",
    "send_interrupt",
    "send_broadcast",
    "task_complete",
]


class AgentToolCall(BaseModel):
    tool_name: str
    tool_args: dict[str, Any]
    tool_call_id: str
    completion: dict[str, Any]

    def create_response_msg(self, content: str) -> dict[str, str]:
        return {
            "role": "tool",
            "name": self.tool_name,
            "content": content,
            "tool_call_id": self.tool_call_id,
        }


def convert_call_to_mail_message(
    call: AgentToolCall, sender: str, task_id: str
) -> MAILMessage:
    """Convert a MAIL tool call to a MAIL message."""
    # Convert sender string to MAILAddress (assuming it's an agent)
    sender_address = create_agent_address(sender)

    match call.tool_name:
        case "send_request":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                message=MAILRequest(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=create_agent_address(call.tool_args["target"]),
                    subject=call.tool_args["subject"],
                    body=call.tool_args["message"],
                    sender_swarm=None,
                    recipient_swarm=None,
                    routing_info=None,
                ),
                msg_type="request",
            )
        case "send_response":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                message=MAILResponse(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=create_agent_address(call.tool_args["target"]),
                    subject=call.tool_args["subject"],
                    body=call.tool_args["message"],
                    sender_swarm=None,
                    recipient_swarm=None,
                    routing_info=None,
                ),
                msg_type="response",
            )
        case "send_interrupt":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                message=MAILInterrupt(
                    task_id=task_id,
                    interrupt_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address(call.tool_args["target"])],
                    subject=call.tool_args["subject"],
                    body=call.tool_args["message"],
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info=None,
                ),
                msg_type="interrupt",
            )
        case "send_broadcast":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                message=MAILBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address("all")],
                    subject=call.tool_args["subject"],
                    body=call.tool_args["message"],
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info=None,
                ),
                msg_type="broadcast",
            )
        case "task_complete":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                message=MAILBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address("all")],
                    subject="Task complete",
                    body=call.tool_args["finish_message"],
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info=None,
                ),
                msg_type="broadcast_complete",
            )
        case _:
            raise ValueError(f"Unknown tool name: {call.tool_name}")


def action_complete_broadcast(
    result_message: dict[str, Any], system_name: str,recipient: str, task_id: str
) -> MAILMessage:
    """Create a MAIL broadcast message to indicate that an action has been completed."""

    return MAILMessage(
        id=str(uuid4()),
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        message=MAILBroadcast(
            task_id=task_id,
            broadcast_id=str(uuid4()),
            sender=create_system_address(system_name),
            recipients=[create_agent_address(recipient)],
            subject=f"Action Complete: {result_message['name']}",
            body=f"The action {result_message['name']} has been completed. The result is as follows:\n\n<output>\n{result_message}\n</output",
            sender_swarm=None,
            recipient_swarms=None,
            routing_info=None,
        ),
        msg_type="broadcast",
    )


def create_request_tool(
    targets: list[str], enable_interswarm: bool = False
) -> dict[str, Any]:
    """Create a MAIL message tool to send messages to specific agents."""

    class send_request(BaseModel):
        """Send a message to a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the message. Must be one of: {', '.join(targets)}"
            + (
                f", or use 'agent-name@swarm-name' format for interswarm messaging"
                if enable_interswarm
                else ""
            )
        )
        subject: str = Field(description="The subject of the message.")
        message: str = Field(description="The message content to send.")

    tool_dict = function_to_dict(send_request)

    target_param = tool_dict["parameters"]["properties"]["target"]
    if enable_interswarm:
        # For interswarm messaging, we don't restrict to enum values
        # The validation will happen at runtime
        target_param["description"] = (
            target_param["description"]
            + " (supports interswarm format: agent-name@swarm-name)"
        )
    else:
        target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


def create_response_tool(
    targets: list[str], enable_interswarm: bool = False
) -> dict[str, Any]:
    """Create a MAIL message tool to send messages to specific agents."""

    class send_response(BaseModel):
        """Send a message to a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the message. Must be one of: {', '.join(targets)}"
            + (
                f", or use 'agent-name@swarm-name' format for interswarm messaging"
                if enable_interswarm
                else ""
            )
        )
        subject: str = Field(description="The subject of the message.")
        message: str = Field(description="The message content to send.")

    tool_dict = function_to_dict(send_response)

    target_param = tool_dict["parameters"]["properties"]["target"]
    if enable_interswarm:
        # For interswarm messaging, we don't restrict to enum values
        # The validation will happen at runtime
        target_param["description"] = (
            target_param["description"]
            + " (supports interswarm format: agent-name@swarm-name)"
        )
    else:
        target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


def create_interrupt_tool(
    targets: list[str], enable_interswarm: bool = False
) -> dict[str, Any]:
    """Create a MAIL interrupt tool to interrupt specific agents."""

    class send_interrupt(BaseModel):
        """Interrupt a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the interrupt. Must be one of: {', '.join(targets)}"
            + (
                f", or use 'agent-name@swarm-name' format for interswarm messaging"
                if enable_interswarm
                else ""
            )
        )
        subject: str = Field(description="The subject of the interrupt.")
        message: str = Field(description="The message content to send.")

    tool_dict = function_to_dict(send_interrupt)

    target_param = tool_dict["parameters"]["properties"]["target"]
    if enable_interswarm:
        target_param["description"] = (
            target_param["description"]
            + " (supports interswarm format: agent-name@swarm-name)"
        )
    else:
        target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


def create_interswarm_broadcast_tool() -> dict[str, Any]:
    """Create a MAIL broadcast tool for interswarm communication."""

    class send_interswarm_broadcast(BaseModel):
        """Broadcast a message to all known swarms."""

        subject: str = Field(description="The subject of the broadcast.")
        message: str = Field(description="The message content to send.")
        target_swarms: list[str] = Field(
            description="List of target swarm names. If empty, broadcasts to all known swarms.",
            default=[],
        )

    return function_to_dict(send_interswarm_broadcast)


def create_swarm_discovery_tool() -> dict[str, Any]:
    """Create a tool for discovering and registering swarms."""

    class discover_swarms(BaseModel):
        """Discover and register new swarms from discovery endpoints."""

        discovery_urls: list[str] = Field(
            description="List of URLs to discover swarms from."
        )

    return function_to_dict(discover_swarms)


def create_broadcast_tool() -> dict[str, Any]:
    """Create a MAIL broadcast tool to broadcast messages to all agents."""

    class send_broadcast(BaseModel):
        """Broadcast a message to all possible recipient agents."""

        subject: str = Field(description="The subject of the broadcast.")
        message: str = Field(description="The message content to send.")

    return function_to_dict(send_broadcast)


def create_acknowledge_broadcast_tool() -> dict[str, Any]:
    """Create a tool for agents to acknowledge a broadcast without replying.

    When invoked, the runtime will store the incoming broadcast in the agent's
    memory and will not emit any outgoing MAIL message.
    """

    class acknowledge_broadcast(BaseModel):
        """Store the received broadcast in memory, do not respond."""

        # Use Optional to avoid PEP 604 UnionType issues in some converters
        note: Optional[str] = Field(
            default=None,
            description="Optional note to include in internal memory only.",
        )

    return function_to_dict(acknowledge_broadcast)


def create_ignore_broadcast_tool() -> dict[str, Any]:
    """Create a tool for agents to ignore a broadcast entirely.

    When invoked, the runtime will neither store nor respond to the broadcast.
    """

    class ignore_broadcast(BaseModel):
        """Ignore the received broadcast. No memory, no response."""

        # Use Optional to avoid PEP 604 UnionType issues in some converters
        reason: Optional[str] = Field(
            default=None,
            description="Optional internal reason for ignoring (not sent).",
        )

    return function_to_dict(ignore_broadcast)


def create_task_complete_tool() -> dict[str, Any]:
    """Create a MAIL task complete tool to indicate that a task has been completed."""

    class task_complete(BaseModel):
        """Indicate that a task has been completed. This will end the current loop, and should always be the last tool called."""

        finish_message: str = Field(
            description="The message to broadcast to all agents to indicate that the task has been completed."
        )

    return function_to_dict(task_complete)


def create_mail_tools(
    targets: list[str], enable_interswarm: bool = False
) -> list[dict[str, Any]]:
    """Create MAIL tools. These should be used for all agents."""
    return [
        create_request_tool(targets, enable_interswarm),
        create_response_tool(targets, enable_interswarm),
        create_acknowledge_broadcast_tool(),
        create_ignore_broadcast_tool(),
    ]


def create_supervisor_tools(
    targets: list[str], can_complete_tasks: bool = True, enable_interswarm: bool = False
) -> list[dict[str, Any]]:
    """Create MAIL supervisor tools. Targets are the agents that the supervisor can send messages to."""

    tools = [
        create_interrupt_tool(targets, enable_interswarm),
        create_broadcast_tool(),
    ]

    if enable_interswarm:
        tools.extend(
            [
                create_interswarm_broadcast_tool(),
                create_swarm_discovery_tool(),
            ]
        )

    if can_complete_tasks:
        tools.append(create_task_complete_tool())

    return tools
