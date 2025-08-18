from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

from .message import (
    ACPBroadcast,
    ACPInterrupt,
    ACPMessage,
    ACPRequest,
    ACPResponse,
    create_agent_address,
    create_system_address,
    create_user_address,
)
from .factories.base import AgentToolCall

ACP_TOOL_NAMES = [
    "send_request",
    "send_response",
    "send_interrupt",
    "send_broadcast",
    "task_complete",
]


def convert_call_to_acp_message(
    call: AgentToolCall, sender: str, task_id: str
) -> ACPMessage:
    """Convert an ACP tool call to an ACP message."""
    # Convert sender string to ACPAddress (assuming it's an agent)
    sender_address = create_agent_address(sender)

    match call.tool_name:
        case "send_request":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now().isoformat(),
                message=ACPRequest(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=create_agent_address(call.tool_args["target"]),
                    header=call.tool_args["header"],
                    body=call.tool_args["message"],
                ),
                msg_type="request",
            )
        case "send_response":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now().isoformat(),
                message=ACPResponse(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=create_agent_address(call.tool_args["target"]),
                    header=call.tool_args["header"],
                    body=call.tool_args["message"],
                ),
                msg_type="response",
            )
        case "send_interrupt":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now().isoformat(),
                message=ACPInterrupt(
                    task_id=task_id,
                    interrupt_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address(call.tool_args["target"])],
                    header=call.tool_args["header"],
                    body=call.tool_args["message"],
                ),
                msg_type="interrupt",
            )
        case "send_broadcast":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now().isoformat(),
                message=ACPBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address("all")],
                    header=call.tool_args["header"],
                    body=call.tool_args["message"],
                ),
                msg_type="broadcast",
            )
        case "task_complete":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now().isoformat(),
                message=ACPBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address("all")],
                    header="Task complete",
                    body=call.tool_args["finish_message"],
                ),
                msg_type="broadcast_complete",
            )
        case _:
            raise ValueError(f"Unknown tool name: {call.tool_name}")


def action_complete_broadcast(
    result_message: dict[str, Any], recipient: str, task_id: str
) -> ACPMessage:
    """Create an ACP broadcast message to indicate that an action has been completed."""

    return ACPMessage(
        id=str(uuid4()),
        timestamp=datetime.now().isoformat(),
        message=ACPBroadcast(
            task_id=task_id,
            broadcast_id=str(uuid4()),
            sender=create_system_address("system"),
            recipients=[create_agent_address(recipient)],
            header=f"Action Complete: {result_message['name']}",
            body=f"The action {result_message['name']} has been completed. The result is as follows:\n\n<output>\n{result_message}\n</output",
        ),
        msg_type="broadcast",
    )


def create_request_tool(
    targets: list[str], enable_interswarm: bool = False
) -> dict[str, Any]:
    """Create an ACP message tool to send messages to specific agents."""

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
        header: str = Field(description="The header of the message.")
        message: str = Field(description="The message content to send.")

    tool_dict = convert_to_openai_tool(send_request)

    target_param = tool_dict["function"]["parameters"]["properties"]["target"]
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
    """Create an ACP message tool to send messages to specific agents."""

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
        header: str = Field(description="The header of the message.")
        message: str = Field(description="The message content to send.")

    tool_dict = convert_to_openai_tool(send_response)

    target_param = tool_dict["function"]["parameters"]["properties"]["target"]
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
    """Create an ACP interrupt tool to interrupt specific agents."""

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
        header: str = Field(description="The header of the interrupt.")
        message: str = Field(description="The message content to send.")

    tool_dict = convert_to_openai_tool(send_interrupt)

    target_param = tool_dict["function"]["parameters"]["properties"]["target"]
    if enable_interswarm:
        target_param["description"] = (
            target_param["description"]
            + " (supports interswarm format: agent-name@swarm-name)"
        )
    else:
        target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


def create_interswarm_broadcast_tool() -> dict[str, Any]:
    """Create an ACP broadcast tool for interswarm communication."""

    class send_interswarm_broadcast(BaseModel):
        """Broadcast a message to all known swarms."""

        header: str = Field(description="The header of the broadcast.")
        message: str = Field(description="The message content to send.")
        target_swarms: list[str] = Field(
            description="List of target swarm names. If empty, broadcasts to all known swarms.",
            default=[],
        )

    return convert_to_openai_tool(send_interswarm_broadcast)


def create_swarm_discovery_tool() -> dict[str, Any]:
    """Create a tool for discovering and registering swarms."""

    class discover_swarms(BaseModel):
        """Discover and register new swarms from discovery endpoints."""

        discovery_urls: list[str] = Field(
            description="List of URLs to discover swarms from."
        )

    return convert_to_openai_tool(discover_swarms)


def create_broadcast_tool() -> dict[str, Any]:
    """Create an ACP broadcast tool to broadcast messages to all agents."""

    class send_broadcast(BaseModel):
        """Broadcast a message to all possible recipient agents."""

        header: str = Field(description="The header of the broadcast.")
        message: str = Field(description="The message content to send.")

    return convert_to_openai_tool(send_broadcast)


def create_task_complete_tool() -> dict[str, Any]:
    """Create an ACP task complete tool to indicate that a task has been completed."""

    class task_complete(BaseModel):
        """Indicate that a task has been completed. This will end the current loop, and should always be the last tool called."""

        finish_message: str = Field(
            description="The message to broadcast to all agents to indicate that the task has been completed."
        )

    return convert_to_openai_tool(task_complete)


def create_supervisor_tools(
    targets: list[str], can_complete_tasks: bool = True, enable_interswarm: bool = False
) -> list[dict[str, Any]]:
    """Create ACP supervisor tools. Targets are the agents that the supervisor can send messages to."""

    tools = [
        create_request_tool(targets, enable_interswarm),
        create_response_tool(targets, enable_interswarm),
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
