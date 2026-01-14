# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import datetime
import logging
from typing import Any, Literal, Optional, cast
from uuid import uuid4

import ujson
from openai import pydantic_function_tool
from openai.resources.responses.responses import _make_tools
from pydantic import BaseModel, Field, model_validator

from .message import (
    MAILBroadcast,
    MAILInterrupt,
    MAILMessage,
    MAILRequest,
    MAILResponse,
    create_agent_address,
)

logger = logging.getLogger("mail.tools")

MAIL_TOOL_NAMES = [
    "send_request",
    "send_response",
    "send_interrupt",
    "send_broadcast",
    "task_complete",
    "acknowledge_broadcast",
    "ignore_broadcast",
    "await_message",
    "help",
]


def get_tool_spec_name(tool: dict[str, Any]) -> str | None:
    """
    Extract the logical tool name from either responses or completions tool specs.
    """
    name = tool.get("name")
    if isinstance(name, str):
        return name
    maybe_function = tool.get("function")
    if isinstance(maybe_function, dict):
        function_name = maybe_function.get("name")
        if isinstance(function_name, str):
            return function_name
    return None


def pydantic_model_to_tool(
    model_cls: type[BaseModel],
    name: str | None = None,
    description: str | None = None,
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Convert a Pydantic model class into an OpenAI function tool spec.

    Returns a dict in the shape expected by Chat Completions and is compatible
    with the Responses API (we later mirror parameters → input_schema when needed).
    """
    completions_tool = pydantic_function_tool(
        model_cls, name=name, description=description
    )
    if style == "completions":
        return cast(dict[str, Any], completions_tool)
    elif style == "responses":
        return _make_tools([completions_tool])[0]  # type: ignore


class AgentToolCall(BaseModel):
    """
    A tool call from an agent.

    Args:
        tool_name: The name of the tool called.
        tool_args: The arguments passed to the tool.
        tool_call_id: The ID of the tool call.
        completion: The full completion of the tool call, if using completions api.
        responses: The full responses list of the tool call, if using responses api.
        reasoning: List of reasoning/thinking text blocks preceding this tool call.
        preamble: Text/message content that appeared before this tool call.
    """

    tool_name: str
    tool_args: dict[str, Any]
    tool_call_id: str
    completion: dict[str, Any] = Field(default_factory=dict)
    responses: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: list[str] | None = None
    preamble: str | None = None

    @model_validator(mode="after")
    def check_completion_or_responses(self):
        if not self.completion and not self.responses:
            raise ValueError(
                "Either 'completion' or 'responses' must be defined (non-empty)."
            )
        return self

    def create_response_msg(self, content: str) -> dict[str, str]:
        if self.completion:
            return {
                "role": "tool",
                "name": self.tool_name,
                "content": content,
                "tool_call_id": self.tool_call_id,
            }
        return {
            "type": "function_call_output",
            "call_id": self.tool_call_id,
            "output": content,
        }


def convert_call_to_mail_message(
    call: AgentToolCall, sender: str, task_id: str
) -> MAILMessage:
    """
    Convert a MAIL tool call to a MAIL message.
    """
    # Convert sender string to MAILAddress (assuming it's an agent)
    sender_address = create_agent_address(sender)

    match call.tool_name:
        case "send_request":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILRequest(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=create_agent_address(call.tool_args["target"]),
                    subject=call.tool_args["subject"],
                    body=call.tool_args["body"],
                    sender_swarm=None,
                    recipient_swarm=None,
                    routing_info={},
                ),
                msg_type="request",
            )
        case "send_response" | "text_output":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILResponse(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=create_agent_address(call.tool_args["target"]),
                    subject=call.tool_args.get("subject", ""),
                    body=call.tool_args.get("body", None)
                    or call.tool_args.get("content", ""),
                    sender_swarm=None,
                    recipient_swarm=None,
                    routing_info={},
                ),
                msg_type="response",
            )
        case "send_interrupt":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILInterrupt(
                    task_id=task_id,
                    interrupt_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address(call.tool_args["target"])],
                    subject=call.tool_args["subject"],
                    body=call.tool_args["body"],
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info={},
                ),
                msg_type="interrupt",
            )
        case "send_broadcast":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address("all")],
                    subject=call.tool_args["subject"],
                    body=call.tool_args["body"],
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info={},
                ),
                msg_type="broadcast",
            )
        case "task_complete":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=[create_agent_address("all")],
                    subject="Task complete",
                    body=call.tool_args["finish_message"],
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info={},
                ),
                msg_type="broadcast_complete",
            )
        case _:
            raise ValueError(f"Unknown tool name: {call.tool_name}")


def normalize_breakpoint_tool_call(
    call: AgentToolCall, raw: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Normalize a breakpoint tool call to Responses-style function_call shape.
    """
    call_id: str | None = None
    name: str | None = None
    arguments: Any = None
    status: str = "completed"
    fc_id: str | None = None

    if isinstance(raw, dict):
        raw_type = raw.get("type")
        if raw_type == "function_call":
            call_id = raw.get("call_id")
            name = raw.get("name")
            arguments = raw.get("arguments")
            status = raw.get("status") or status
            fc_id = raw.get("id")
        elif raw_type == "tool_use":
            call_id = raw.get("id")
            name = raw.get("name")
            arguments = raw.get("input")

    if name is None:
        name = call.tool_name
    if not call_id:
        call_id = call.tool_call_id
    if arguments is None:
        arguments = call.tool_args
    if not isinstance(arguments, str):
        arguments = ujson.dumps(arguments)
    if not fc_id:
        fc_id = f"fc_{call_id}"

    return {
        "arguments": arguments,
        "call_id": call_id,
        "name": name,
        "type": "function_call",
        "id": fc_id,
        "status": status,
    }


def convert_manual_step_call_to_mail_message(
    call: AgentToolCall,
    sender: str,
    task_id: str,
    response_targets: list[str],
    response_type: Literal["broadcast", "response", "request"],
) -> MAILMessage:
    """
    Convert a MAIL tool call to a MAIL message.
    """
    # Convert sender string to MAILAddress (assuming it's an agent)
    sender_address = create_agent_address(sender)
    targets = []
    for target in response_targets:
        if target == "all":
            targets.append(create_agent_address("all"))
        else:
            targets.append(create_agent_address(target))

    match response_type:
        case "request":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILRequest(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=targets[0],
                    subject=call.tool_args.get("subject", ""),
                    body=call.tool_args.get("body", None)
                    or call.tool_args.get("content", ""),
                    sender_swarm=None,
                    recipient_swarm=None,
                    routing_info={},
                ),
                msg_type="request",
            )
        case "response":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILResponse(
                    task_id=task_id,
                    request_id=str(uuid4()),
                    sender=sender_address,
                    recipient=targets[0],
                    subject=call.tool_args.get("subject", ""),
                    body=call.tool_args.get("body", None)
                    or call.tool_args.get("content", ""),
                    sender_swarm=None,
                    recipient_swarm=None,
                    routing_info={},
                ),
                msg_type="response",
            )
        case "broadcast":
            return MAILMessage(
                id=str(uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid4()),
                    sender=sender_address,
                    recipients=targets,
                    subject=call.tool_args.get("subject", ""),
                    body=call.tool_args.get("body", None)
                    or call.tool_args.get("content", ""),
                    sender_swarm=None,
                    recipient_swarms=None,
                    routing_info={},
                ),
                msg_type="broadcast",
            )


def create_request_tool(
    targets: list[str],
    enable_interswarm: bool = False,
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL message tool to send messages to specific agents.
    """

    class send_request(BaseModel):
        """Send a message to a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the message. Must be one of: {', '.join(targets)}"
            + (
                ", or use 'agent-name@swarm-name' format for interswarm messaging"
                if enable_interswarm
                else ""
            )
        )
        subject: str = Field(description="The subject of the message.")
        body: str = Field(description="The message content to send.")

    tool_dict = pydantic_model_to_tool(send_request, name="send_request", style=style)

    target_param = (
        tool_dict["function"]["parameters"]["properties"]["target"]
        if style == "completions"
        else tool_dict["parameters"]["properties"]["target"]
    )
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


SEND_REQUEST_HELP_STRING = """
Send a message to a specific recipient agent (the `target`).
This is useful for initiating a conversation with another agent.

# Example
A MAIL swarm `example` has agents `supervisor` and `weather`.
`supervisor` can interact with the user and complete the task, while `weather` can call the `get_weather_forecast` action.
Say a user creates a task for getting the weather forecast in Tokyo:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>What will the weather be like in Tokyo tomorrow?</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate the task to `weather`:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipient type="agent">weather</recipient>
    <subject>Weather forecast in Tokyo</subject>
    <body>User asked: 'What will the weather be like in Tokyo tomorrow?' Please get the forecast and respond to me with the result.</body>
    <msg_type>request</msg_type>
</message>
```

From there, `weather` can call the `get_weather_forecast` action, and send the result back to `supervisor` in the form of a response.
Finally, `supervisor` can call the `task_complete` tool with the final answer to the user's task (in this case, the weather forecast for Tokyo tomorrow).
"""


def create_response_tool(
    targets: list[str],
    enable_interswarm: bool = False,
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL message tool to send messages to specific agents.
    """

    class send_response(BaseModel):
        """Send a message to a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the message. Must be one of: {', '.join(targets)}"
            + (
                ", or use 'agent-name@swarm-name' format for interswarm messaging"
                if enable_interswarm
                else ""
            )
        )
        subject: str = Field(description="The subject of the message.")
        body: str = Field(description="The message content to send.")

    tool_dict = pydantic_model_to_tool(send_response, name="send_response", style=style)

    target_param = (
        tool_dict["function"]["parameters"]["properties"]["target"]
        if style == "completions"
        else tool_dict["parameters"]["properties"]["target"]
    )
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


SEND_RESPONSE_HELP_STRING = """
Send a message to a specific target recipient agent (the `target`).
This is useful for responding to a message from another agent.

# Example
A MAIL swarm `example` has agents `supervisor` and `math`.
`supervisor` can interact with the user and complete the task, while `math` can call the `calculate_expression` action.
Say a user creates a task for solving the expression `2 * (3 + 4)`:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>What is 2 * (3 + 4)?</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate the task to `math`:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipient type="agent">math</recipient>
    <subject>Math problem</subject>
    <body>User asked: 'What is 2 * (3 + 4)?' Please solve the expression and respond to me with the result.</body>
    <msg_type>request</msg_type>
</message>
```

`math` can then call the `calculate_expression` action, and send the result back to `supervisor` in the form of a response:

```xml
<message>
    <sender type="agent">math</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>Re: Math problem</subject>
    <body>The result is 14.</body>
    <msg_type>response</msg_type>
</message>
```

Finally, `supervisor` can call the `task_complete` tool with the final answer to the user's task (in this case, the result of the expression `2 * (3 + 4)`).
"""


def create_interrupt_tool(
    targets: list[str],
    enable_interswarm: bool = False,
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL interrupt tool to interrupt specific agents.
    """

    class send_interrupt(BaseModel):
        """Interrupt a specific target recipient agent."""

        target: str = Field(
            description=f"The target recipient agent for the interrupt. Must be one of: {', '.join(targets)}"
            + (
                ", or use 'agent-name@swarm-name' format for interswarm messaging"
                if enable_interswarm
                else ""
            )
        )
        subject: str = Field(description="The subject of the interrupt.")
        body: str = Field(description="The message content to send.")

    tool_dict = pydantic_model_to_tool(
        send_interrupt, name="send_interrupt", style=style
    )

    target_param = (
        tool_dict["function"]["parameters"]["properties"]["target"]
        if style == "completions"
        else tool_dict["parameters"]["properties"]["target"]
    )
    if enable_interswarm:
        target_param["description"] = (
            target_param["description"]
            + " (supports interswarm format: agent-name@swarm-name)"
        )
    else:
        target_param["enum"] = targets  # This provides the allowed values to the LLM

    return tool_dict


SEND_INTERRUPT_HELP_STRING = """
Interrupt a specific target recipient agent (the `target`).
This is useful for interrupting a specific agent's execution.

# Example
A MAIL swarm `example` has agents `supervisor` and `wra`.
`supervisor` can interact with the user and complete the task, while `wra` can call the actions `start_web_research` and `fetch_web_research`.
Say a user creates a task to start web research on the topic of "effect of climate change by 2050":

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>Start web research on the topic of "effect of climate change by 2050".</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate the task to `wra`:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipient type="agent">wra</recipient>
    <subject>Web research</subject>
    <body>User asked: 'Start web research on the topic of "effect of climate change by 2050".' Please start the research and respond to me with the result.</body>
    <msg_type>request</msg_type>
</message>
```

From there, `wra` can call `start_web_research` to begin the research process for the user's query.
However, this task is taking too long to complete--perhaps due to API issues.
The user sends an interrupt to `supervisor` to check on the status of the research:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>The web research process is taking too long to complete. Can you check on the status?</body>
    <msg_type>interrupt</msg_type>
</message>
```

`supervisor` can then call the `send_interrupt` tool to interrupt `wra`:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipient type="agent">wra</recipient>
    <subject>Check on web research status</subject>
    <body>The web research process for the query "effect of climate change by 2050" is taking too long to complete. Can you check on the status?</body>
    <msg_type>interrupt</msg_type>
</message>
```

From there, `wra` can call `fetch_web_research` to get the status of the research process.
The agent can then notify `supervisor` of the status of the research process:

```xml
<message>
    <sender type="agent">wra</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>Web research status</subject>
    <body>I checked the status on the web research process. It has not yet completed.</body>
    <msg_type>response</msg_type>
</message>
```

Finally, `supervisor` can call `task_complete` to inform the user of the research process status (in this case, not yet completed).
"""


def create_interswarm_broadcast_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL broadcast tool for interswarm communication.
    """

    class send_interswarm_broadcast(BaseModel):
        """Broadcast a message to all known swarms."""

        subject: str = Field(description="The subject of the broadcast.")
        body: str = Field(description="The message content to send.")
        target_swarms: list[str] = Field(
            description="List of target swarm names. If empty, broadcasts to all known swarms.",
            default=[],
        )

    return pydantic_model_to_tool(
        send_interswarm_broadcast, name="send_interswarm_broadcast", style=style
    )


def create_swarm_discovery_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a tool for discovering and registering swarms.
    """

    class discover_swarms(BaseModel):
        """Discover and register new swarms from discovery endpoints."""

        discovery_urls: list[str] = Field(
            description="List of URLs to discover swarms from."
        )

    return pydantic_model_to_tool(discover_swarms, name="discover_swarms", style=style)


def create_broadcast_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL broadcast tool to broadcast messages to a specified list of agents, or all agents in the swarm.
    """

    class send_broadcast(BaseModel):
        """Broadcast a message to a specified list of agents, or all agents in the swarm."""

        subject: str = Field(description="The subject of the broadcast.")
        body: str = Field(description="The message content to send.")
        targets: list[str] = Field(
            description="The list of agents to broadcast to. Use ['all'] to broadcast to all agents in the swarm."
        )

    return pydantic_model_to_tool(send_broadcast, name="send_broadcast", style=style)


SEND_BROADCAST_HELP_STRING = """
Broadcast a message to a specified list of agents, or all agents in the swarm.
This is useful for disseminating information relevant to the recipients.

# Example
A MAIL swarm `example` has agents `supervisor`, `weather`, and `wra`.
The supervisor can interact with the user and complete the task, while `weather` and `wra` have their own actions.
Say a user creates a task that utilizes both `weather` and `wra`:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>Create a report on the impact of climate change by 2050.</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate specific tasks to `weather` and `wra` before preparing a final response.
`weather` and `wra` may communicate with each other directly, not just through `supervisor`.
However, `weather` does not seem to be working properly--it's unable to process `supervisor`'s messages.
Upon seeing this, `supervisor` sends a broadcast to `wra` to inform it of the issue:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipients>
        <recipient type="agent">wra</recipient>
    </recipients>
    <subject>Weather issue</subject>
    <body>The weather agent is not responding to messages. Keep this in mind when preparing the report. I will let you know if there are any updates.</body>
    <msg_type>broadcast</msg_type>
</message>
```

Alternatively, `supervisor` can send a broadcast to all agents in the swarm (including `weather`):

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipients>
        <recipient type="agent">all</recipient>
    </recipients>
    <subject>Weather issue</subject>
    <body>The weather agent is not responding to messages. Keep this in mind for this task. I will let you know if there are any updates.</body>
    <msg_type>broadcast</msg_type>
</message>
```

Broadcast recipients can then acknowledge the broadcast and continue with their work.
When the user's task is done, `task_complete` is called by `supervisor`.
"""


def create_acknowledge_broadcast_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a tool for agents to acknowledge a broadcast without replying.
    When invoked, the runtime will store the incoming broadcast in the agent's
    memory and will not emit any outgoing MAIL message.
    """

    class acknowledge_broadcast(BaseModel):
        """
        Store the received broadcast in memory, do not respond.
        This MUST NOT be used in response to a message of type other than 'broadcast'.
        Not all broadcasts warrant acknowledgement--only those that do not warrant a response.
        """

        # Use Optional to avoid PEP 604 UnionType issues in some converters
        note: Optional[str] = Field(  # noqa: UP045
            default=None,
            description="Optional note to include in internal memory only.",
        )

    return pydantic_model_to_tool(
        acknowledge_broadcast, name="acknowledge_broadcast", style=style
    )


ACKNOWLEDGE_BROADCAST_HELP_STRING = """
Acknowledge a broadcast and store in memory without replying.
This is useful for cases where a broadcast does not warrant a response message.

# Example
A MAIL swarm `example` has agents `supervisor`, `weather`, and `wra`.
The supervisor can interact with the user and complete the task, while `weather` and `wra` have their own actions.
Say a user creates a task that utilizes both `weather` and `wra`:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>Create a report on the impact of climate change by 2050.</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate specific tasks to `weather` and `wra` before preparing a final response.
`weather` and `wra` may communicate with each other directly, not just through `supervisor`.
However, `weather` does not seem to be working properly--it's unable to process `supervisor`'s messages.
Upon seeing this, `supervisor` sends a broadcast to `wra` to inform it of the issue:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipients>
        <recipient type="agent">wra</recipient>
    </recipients>
    <subject>Weather issue</subject>
    <body>The weather agent is not responding to messages. Keep this in mind when preparing the report. I will let you know if there are any updates.</body>
    <msg_type>broadcast</msg_type>
</message>
```

Upon receiving the broadcast, `wra` can acknowledge the broadcast without replying:

```python
acknowledge_broadcast(note="Acknowledged that `weather` is not responding to messages.")
```

No response message is sent to `supervisor`, but the broadcast is stored in `wra`'s memory.
From there, the swarm can continue with their work until `task_complete` is called by `supervisor`.
"""


def create_ignore_broadcast_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a tool for agents to ignore a broadcast entirely.
    When invoked, the runtime will neither store nor respond to the broadcast.
    """

    class ignore_broadcast(BaseModel):
        """Ignore the received broadcast. No memory, no response."""

        # Use Optional to avoid PEP 604 UnionType issues in some converters
        reason: Optional[str] = Field(  # noqa: UP045
            default=None,
            description="Optional internal reason for ignoring (not sent).",
        )

    return pydantic_model_to_tool(
        ignore_broadcast, name="ignore_broadcast", style=style
    )


IGNORE_BROADCAST_HELP_STRING = """
Ignore a broadcast by not storing or responding to it.
This is useful for cases where a broadcast does not warrant a response message.
Note that the broadcast itself is not saved, but the tool call is.

# Example
A MAIL swarm `example` has agents `supervisor`, `weather`, and `wra`.
The supervisor can interact with the user and complete the task, while `weather` and `wra` have their own actions.
`supervisor` can communicate with both `weather` and `wra` directly, but `weather` and `wra` cannot communicate with each other.
Say a user creates a task that utilizes both `weather` and `wra`:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>Create a report on the impact of climate change by 2050.</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate specific tasks to `weather` and `wra` before preparing a final response.
`weather` and `wra` may communicate with each other directly, not just through `supervisor`.
However, `weather` does not seem to be working properly--it's unable to process `supervisor`'s messages.
Upon seeing this, `supervisor` sends a broadcast to `wra` to inform it of the issue:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipients>
        <recipient type="agent">wra</recipient>
    </recipients>
    <subject>Weather issue</subject>
    <body>The weather agent is not responding to messages. Keep this in mind when preparing the report. I will let you know if there are any updates.</body>
    <msg_type>broadcast</msg_type>
</message>
```

However, since `weather` and `wra` cannot communicate with each other, `wra` can ignore the broadcast without replying:

```python
ignore_broadcast(reason="`weather` is not responding to messages.")
```

No response message is sent to `supervisor`, but the broadcast is ignored.
No broadcast is saved in `wra`'s memory, but the tool call is.
From there, the swarm can continue with their work until `task_complete` is called by `supervisor`.
"""


def create_task_complete_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL task complete tool to indicate that a task has been completed.
    """

    class task_complete(BaseModel):
        """Indicate that a task has been completed. This will end the current loop, and should always be the last tool called."""

        finish_message: str = Field(
            description="""The final response to the user's task.
Since the user cannot see the swarm's communication, you MUST include the full answer to the user's task.
Furthermore, this broadcast will be sent to all agents in the swarm to notify them that the task has been completed.
"""
        )

    return pydantic_model_to_tool(task_complete, name="task_complete", style=style)


TASK_COMPLETE_HELP_STRING = """
Indicate that the current task has been completed, and provide the user a final response.
This will end the current loop, and should always be the last tool called.

# Example
A MAIL swarm `example` has agents `supervisor` and `weather`.
The supervisor can interact with the user and complete the task, while `weather` can call the `get_weather_forecast` action.
Say a user creates a task for getting the weather forecast in Tokyo:

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>What will the weather be like in Tokyo tomorrow?</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate the task to `weather`:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipient type="agent">weather</recipient>
    <subject>Weather forecast in Tokyo</subject>
    <body>User asked: 'What will the weather be like in Tokyo tomorrow?' Please get the forecast and respond to me with the result.</body>
    <msg_type>request</msg_type>
</message>
```

From there, `weather` can call the `get_weather_forecast` action and send the result back to `supervisor` in the form of a response:

```xml
<message>
    <sender type="agent">weather</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>Re: Weather forecast in Tokyo</subject>
    <body>The weather forecast for Tokyo tomorrow is sunny with a temperature of 20 degrees Celsius.</body>
    <msg_type>response</msg_type>
</message>
```

Finally, `supervisor` can call the `task_complete` tool with the final answer to the user's task (in this case, the weather forecast for Tokyo tomorrow).

```python
task_complete(finish_message="The weather forecast for Tokyo tomorrow is sunny with a temperature of 20 degrees Celsius.")
```

The finish message will be sent to the user.
Furthermore, the finish message will be sent to all agents in the swarm to notify them that the task has been completed:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipients>
        <recipient type="agent">all</recipient>
    </recipients>
    <subject>Re: Weather forecast in Tokyo</subject>
    <body>The weather forecast for Tokyo tomorrow is sunny with a temperature of 20 degrees Celsius.</body>
    <msg_type>broadcast_complete</msg_type>
</message>
```

Note that the broadcast_complete saved in agent memory for all recipients, but no recipients are reprompted.
The `task_complete` call shuts down the task runtime.
"""


def create_await_message_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL await message tool to wait for a message.
    """

    class await_message(BaseModel):
        """Wait until another message is received."""

        reason: Optional[str] = Field(  # noqa: UP045
            default=None,
            description="Optional reason for waiting.",
        )

    return pydantic_model_to_tool(await_message, name="await_message", style=style)


AWAIT_MESSAGE_HELP_STRING = """
Wait until another message is received.
This is useful for cases where an agent needs to wait for a message before continuing.

# Example
A MAIL swarm `example` has agents `supervisor` and `wra`.
The supervisor can interact with the user and complete the task, while `wra` can call the `perform_web_research` action.
Say a user creates a task for performing web research on the topic of "economic impact of AI by 2030":

```xml
<message>
    <sender type="user">example_user</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>New Message</subject>
    <body>Perform web research on the topic of "economic impact of AI by 2030".</body>
    <msg_type>request</msg_type>
</message>
```

`supervisor` can then delegate the task to `wra`:

```xml
<message>
    <sender type="agent">supervisor</sender>
    <recipient type="agent">wra</recipient>
    <subject>Web research</subject>
    <body>User asked: 'Perform web research on the topic of "economic impact of AI by 2030".' Please perform the research and respond to me with the result.</body>
    <msg_type>request</msg_type>
</message>
```

From there, `wra` can call the `perform_web_research` action, and respond to `supervisor` to inform it that the research has started:

```xml
<message>
    <sender type="agent">wra</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>Web research</subject>
    <body>I have started the web research. When the process is complete, I will respond to you with the result.</body>
    <msg_type>response</msg_type>
</message>
```

In this case, `supervisor` has nothing else to do before research is complete.
Since `wra` will receive an '::action_complete_broadcast::' message when the research is complete, `supervisor` can call the `await_message` tool to wait for `wra`'s response:

```python
await_message(reason="Waiting for wra's response.")
```

When `perform_web_research` is complete, `wra` will respond to `supervisor` with the result of the research:

```xml
<message>
    <sender type="agent">wra</sender>
    <recipient type="agent">supervisor</recipient>
    <subject>Web research</subject>
    <body>The result of the web research is as follows. ...</body>
    <msg_type>response</msg_type>
</message>
```

This reprompts `supervisor`, who can proceed with the task until completion.
"""


def create_help_tool(
    style: Literal["completions", "responses"] = "completions",
) -> dict[str, Any]:
    """
    Create a MAIL help tool to get help with MAIL.
    """

    class help(BaseModel):
        """Get help with MAIL."""

        get_summary: bool = Field(
            default=True, description="Whether to get a short summary of MAIL."
        )
        get_identity: bool = Field(
            default=False,
            description="Whether to get your identity (agent name, swarm, etc.).",
        )
        get_tool_help: list[
            Literal[
                "send_request",
                "send_response",
                "send_broadcast",
                "send_interrupt",
                "acknowledge_broadcast",
                "ignore_broadcast",
                "await_message",
                "task_complete",
            ]
        ] = Field(default=[], description="The tools to get help for.")
        get_full_protocol: bool = Field(
            default=False,
            description="Whether to get the full MAIL protocol specification.",
        )

    return pydantic_model_to_tool(help, name="help", style=style)


def create_mail_tools(
    targets: list[str],
    enable_interswarm: bool = False,
    style: Literal["completions", "responses"] = "completions",
    exclude_tools: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Create MAIL tools. These should be used for all agents.

    Args:
        targets: The agents that the agent can send messages to.
        enable_interswarm: Whether the agent can send interswarm messages.
        style: The style of the tools to create.
        exclude_tools: The names of MAIL tools that should not be available.
    """
    exclude_tools = exclude_tools or []
    all_tools = [
        create_request_tool(targets, enable_interswarm, style),
        create_response_tool(targets, enable_interswarm, style),
        create_acknowledge_broadcast_tool(style),
        create_ignore_broadcast_tool(style),
        create_await_message_tool(style),
        create_help_tool(style),
    ]

    # filter out the excluded tools
    final_tools: list[dict[str, Any]] = []
    for tool in all_tools:
        tool_name = get_tool_spec_name(tool)
        if tool_name is None or tool_name not in exclude_tools:
            final_tools.append(tool)

    return final_tools


def create_supervisor_tools(
    targets: list[str],
    can_complete_tasks: bool = True,
    enable_interswarm: bool = False,
    exclude_tools: list[str] | None = None,
    style: Literal["completions", "responses"] = "completions",
    _debug_include_intraswarm: bool = True,
) -> list[dict[str, Any]]:
    """
    Create MAIL supervisor-exclusive tools.

    Args:
        targets: The agents that the supervisor can send messages to.
        can_complete_tasks: Whether the supervisor can complete tasks.
        enable_interswarm: Whether the supervisor can send interswarm messages.
        exclude_tools: The names of MAIL tools that should not be available.
        style: The style of the tools to create.
    """
    exclude_tools = exclude_tools or []
    tools: list[dict[str, Any]] = []
    if _debug_include_intraswarm:
        tools += [
            create_interrupt_tool(targets, enable_interswarm, style),
            create_broadcast_tool(style),
        ]

    if enable_interswarm:
        tools += [
            create_interswarm_broadcast_tool(style),
            create_swarm_discovery_tool(style),
        ]

    if can_complete_tasks:
        tools.append(create_task_complete_tool(style))

    # filter out the excluded tools
    final_tools: list[dict[str, Any]] = []
    for tool in tools:
        tool_name = get_tool_spec_name(tool)
        if tool_name is None or tool_name not in exclude_tools:
            final_tools.append(tool)

    return final_tools


def get_tool_help(
    tools: list[str],
) -> str:
    """
    Create a MAIL tools help string for the given list of tool names.
    """
    result = ""
    for tool in tools:
        match tool:
            case "send_request":
                tool_help = SEND_REQUEST_HELP_STRING
            case "send_response":
                tool_help = SEND_RESPONSE_HELP_STRING
            case "send_broadcast":
                tool_help = SEND_BROADCAST_HELP_STRING
            case "send_interrupt":
                tool_help = SEND_INTERRUPT_HELP_STRING
            case "acknowledge_broadcast":
                tool_help = ACKNOWLEDGE_BROADCAST_HELP_STRING
            case "ignore_broadcast":
                tool_help = IGNORE_BROADCAST_HELP_STRING
            case "await_message":
                tool_help = AWAIT_MESSAGE_HELP_STRING
            case "task_complete":
                tool_help = TASK_COMPLETE_HELP_STRING
            case _:
                raise ValueError(f"unknown tool name: {tool}")

        result += f"===== Tool `{tool}` =====\n{tool_help}\n\n"

    return result
