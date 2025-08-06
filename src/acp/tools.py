from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

from acp.message import (
    ACPBroadcast,
    ACPInterrupt,
    ACPMessage,
    ACPRequest,
    ACPResponse,
)
from acp.factories.base import AgentToolCall

ACP_TOOL_NAMES = ["send_message", "send_interrupt", "send_broadcast", "task_complete"]


def convert_call_to_acp_message(
    call: AgentToolCall, sender: str, req_id: str | None = None
) -> ACPMessage:
    """Convert an ACP tool call to an ACP message."""
    match call.tool_name:
        case "send_message":
            if not req_id:
                return ACPMessage(
                    id=str(uuid4()),
                    timestamp=datetime.now(),
                    message=ACPRequest(
                        request_id=str(uuid4()),
                        sender=sender,
                        recipient=call.tool_args["target"],
                        header=call.tool_args["header"],
                        body=call.tool_args["message"],
                    ),
                    msg_type="request",
                )
            else:
                return ACPMessage(
                    id=req_id,
                    timestamp=datetime.now(),
                    message=ACPResponse(
                        request_id=str(uuid4()),
                        sender=sender,
                        recipient=call.tool_args["target"],
                        header=call.tool_args["header"],
                        body=call.tool_args["message"],
                    ),
                    msg_type="response",
                )
        case "send_interrupt":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now(),
                message=ACPInterrupt(
                    interrupt_id=str(uuid4()),
                    sender=sender,
                    recipients=[call.tool_args["target"]],
                    header=call.tool_args["header"],
                    body=call.tool_args["message"],
                ),
                msg_type="interrupt",
            )
        case "send_broadcast":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now(),
                message=ACPBroadcast(
                    broadcast_id=str(uuid4()),
                    sender=sender,
                    recipients=["all"],
                    header=call.tool_args["header"],
                    body=call.tool_args["message"],
                ),
                msg_type="broadcast",
            )
        case "task_complete":
            return ACPMessage(
                id=str(uuid4()),
                timestamp=datetime.now(),
                message=ACPBroadcast(
                    broadcast_id=str(uuid4()),
                    sender=sender,
                    recipients=["all"],
                    header="Task complete",
                    body=call.tool_args["finish_message"],
                ),
                msg_type="broadcast_complete",
            )
        case _:
            raise ValueError(f"Unknown tool name: {call.tool_name}")


def action_complete_broadcast(
    result_message: dict[str, Any], recipient: str
) -> ACPMessage:
    """Create an ACP broadcast message to indicate that an action has been completed."""

    return ACPMessage(
        id=str(uuid4()),
        timestamp=datetime.now(),
        message=ACPBroadcast(
            broadcast_id=str(uuid4()),
            sender="system",
            recipients=[recipient],
            header=f"Action Complete: {result_message['name']}",
            body=f"The action {result_message['name']} has been completed. The result is as follows:\n\n<output>\n{result_message}\n</output",
        ),
        msg_type="broadcast",
    )


def create_message_tool(targets: list[str]) -> dict[str, Any]:
    """Create an ACP message tool to send messages to specific agents."""

    class send_message(BaseModel):
        """Send a message to a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the message. Must be one of: {', '.join(targets)}"
        )
        header: str = Field(description="The header of the message.")
        message: str = Field(description="The message content to send.")

    tool_dict = convert_to_openai_tool(send_message)

    target_param = tool_dict["function"]["parameters"]["properties"]["target"]
    target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


def create_interrupt_tool(targets: list[str]) -> dict[str, Any]:
    """Create an ACP interrupt tool to interrupt specific agents."""

    class send_interrupt(BaseModel):
        """Interrupt a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the interrupt. Must be one of: {', '.join(targets)}"
        )
        header: str = Field(description="The header of the interrupt.")
        message: str = Field(description="The message content to send.")

    tool_dict = convert_to_openai_tool(send_interrupt)

    target_param = tool_dict["function"]["parameters"]["properties"]["target"]
    target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


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
    targets: list[str], can_complete_tasks: bool = False
) -> list[dict[str, Any]]:
    """Create ACP supervisor tools. Targets are the agents that the supervisor can send messages to."""

    tools = [
        create_message_tool(targets),
        create_interrupt_tool(targets),
        create_broadcast_tool(),
    ]

    if can_complete_tasks:
        tools.append(create_task_complete_tool())

    return tools
