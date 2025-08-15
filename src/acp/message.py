from datetime import datetime
from typing import Any, Literal, TypedDict, Optional

from dict2xml import dict2xml


class ACPRequest(TypedDict):
    """A request to an agent using the ACP protocol."""

    task_id: str
    """The unique identifier for the task."""

    request_id: str
    """The unique identifier for the request."""

    sender: str
    """The sender of the request."""

    recipient: str
    """The recipient of the request."""

    header: str
    """The subject of the request."""

    body: str
    """The body of the request."""

    # Interswarm fields
    sender_swarm: Optional[str]
    """The swarm name of the sender (for interswarm messages)."""

    recipient_swarm: Optional[str]
    """The swarm name of the recipient (for interswarm messages)."""

    routing_info: Optional[dict[str, Any]]
    """Additional routing information for interswarm messages."""


class ACPResponse(TypedDict):
    """A response from an agent using the ACP protocol."""

    task_id: str
    """The unique identifier for the task."""

    request_id: str
    """The unique identifier of the request being responded to."""

    sender: str
    """The sender of the response."""

    recipient: str
    """The recipient of the response."""

    header: str
    """The status of the response."""

    body: str
    """The body of the response."""

    # Interswarm fields
    sender_swarm: Optional[str]
    """The swarm name of the sender (for interswarm messages)."""

    recipient_swarm: Optional[str]
    """The swarm name of the recipient (for interswarm messages)."""

    routing_info: Optional[dict[str, Any]]
    """Additional routing information for interswarm messages."""


class ACPBroadcast(TypedDict):
    """A broadcast message using the ACP protocol."""

    task_id: str
    """The unique identifier for the task."""

    broadcast_id: str
    """The unique identifier for the broadcast."""

    sender: str
    """The sender of the broadcast."""

    recipients: list[str]
    """The recipients of the broadcast."""

    header: str
    """The subject of the broadcast."""

    body: str
    """The full details of the broadcast."""

    # Interswarm fields
    sender_swarm: Optional[str]
    """The swarm name of the sender (for interswarm messages)."""

    recipient_swarms: Optional[list[str]]
    """The swarm names of the recipients (for interswarm messages)."""

    routing_info: Optional[dict[str, Any]]
    """Additional routing information for interswarm messages."""


class ACPInterrupt(TypedDict):
    """An interrupt using the ACP protocol."""

    task_id: str
    """The unique identifier for the task."""

    interrupt_id: str
    """The unique identifier for the interrupt."""

    sender: str
    """The sender of the interrupt."""

    recipients: list[str]
    """The recipients of the interrupt."""

    header: str
    """The description of the interrupt."""

    body: str
    """The full details of the interrupt, including what tasks to halt, conditions for resuming, and if interrupted tasks should be discarded."""

    # Interswarm fields
    sender_swarm: Optional[str]
    """The swarm name of the sender (for interswarm messages)."""

    recipient_swarms: Optional[list[str]]
    """The swarm names of the recipients (for interswarm messages)."""

    routing_info: Optional[dict[str, Any]]
    """Additional routing information for interswarm messages."""


class ACPInterswarmMessage(TypedDict):
    """An interswarm message wrapper for HTTP transport."""

    message_id: str
    """The unique identifier for the interswarm message."""

    source_swarm: str
    """The source swarm name."""

    target_swarm: str
    """The target swarm name."""

    timestamp: str
    """The timestamp of the message."""

    payload: ACPRequest | ACPResponse | ACPBroadcast | ACPInterrupt
    """The wrapped ACP message."""

    msg_type: Literal["request", "response", "broadcast", "interrupt"]
    """The type of the message."""

    auth_token: Optional[str]
    """Authentication token for interswarm communication."""

    metadata: Optional[dict[str, Any]]
    """Additional metadata for routing and processing."""


def parse_agent_address(address: str) -> tuple[str, Optional[str]]:
    """
    Parse an agent address in the format 'agent-name' or 'agent-name@swarm-name'.
    
    Returns:
        tuple: (agent_name, swarm_name or None)
    """
    if "@" in address:
        agent_name, swarm_name = address.split("@", 1)
        return agent_name.strip(), swarm_name.strip()
    else:
        return address.strip(), None


def format_agent_address(agent_name: str, swarm_name: Optional[str] = None) -> str:
    """
    Format an agent address from agent name and optional swarm name.
    
    Returns:
        str: Formatted address
    """
    if swarm_name:
        return f"{agent_name}@{swarm_name}"
    else:
        return agent_name


def build_body_xml(content: dict[str, Any]) -> str:
    """Build the XML representation an ACP body section."""
    return str(dict2xml(content, wrap="body", indent=""))


def build_acp_xml(message: "ACPMessage") -> dict[str, str]:
    """Build the XML representation of an ACP message."""
    to = (
        message["message"]["recipient"]  # type: ignore
        if "recipient" in message["message"]
        else message["message"]["recipients"]
    )
    return {
        "role": "user",
        "content": f"""
<incoming_message>
<timestamp>{message["timestamp"]}</timestamp>
<from>{message["message"]["sender"]}</from>
<to>{to}</to>
<header>{message["message"]["header"]}</header>
<body>{message["message"]["body"]}</body>
</incoming_message>
""",
    }


class ACPMessage(TypedDict):
    """A message using the ACP protocol."""

    id: str
    """The unique identifier for the message."""

    timestamp: str
    """The timestamp of the message."""

    message: ACPRequest | ACPResponse | ACPBroadcast | ACPInterrupt
    """The message content."""

    msg_type: Literal[
        "request", "response", "broadcast", "interrupt", "broadcast_complete"
    ]
    """The type of the message."""
