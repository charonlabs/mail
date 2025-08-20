import datetime
from typing import Any, Literal, TypedDict, Optional

from dict2xml import dict2xml


class MAILAddress(TypedDict):
    """An address representing the sender or recipient of a MAIL message."""

    address_type: Literal["agent", "user", "system"]
    """The type of address."""

    address: str
    """The address of the sender or recipient."""


class MAILRequest(TypedDict):
    """A request to an agent using the MAIL protocol."""

    task_id: str
    """The unique identifier for the task."""

    request_id: str
    """The unique identifier for the request."""

    sender: MAILAddress
    """The sender of the request."""

    recipient: MAILAddress
    """The recipient of the request."""

    subject: str
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


class MAILResponse(TypedDict):
    """A response from an agent using the MAIL protocol."""

    task_id: str
    """The unique identifier for the task."""

    request_id: str
    """The unique identifier of the request being responded to."""

    sender: MAILAddress
    """The sender of the response."""

    recipient: MAILAddress
    """The recipient of the response."""

    subject: str
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


class MAILBroadcast(TypedDict):
    """A broadcast message using the MAIL protocol."""

    task_id: str
    """The unique identifier for the task."""

    broadcast_id: str
    """The unique identifier for the broadcast."""

    sender: MAILAddress
    """The sender of the broadcast."""

    recipients: list[MAILAddress]
    """The recipients of the broadcast."""

    subject: str
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


class MAILInterrupt(TypedDict):
    """An interrupt using the MAIL protocol."""

    task_id: str
    """The unique identifier for the task."""

    interrupt_id: str
    """The unique identifier for the interrupt."""

    sender: MAILAddress
    """The sender of the interrupt."""

    recipients: list[MAILAddress]
    """The recipients of the interrupt."""

    subject: str
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


class MAILInterswarmMessage(TypedDict):
    """An interswarm message wrapper for HTTP transport."""

    message_id: str
    """The unique identifier for the interswarm message."""

    source_swarm: str
    """The source swarm name."""

    target_swarm: str
    """The target swarm name."""

    timestamp: str
    """The timestamp of the message."""

    payload: MAILRequest | MAILResponse | MAILBroadcast | MAILInterrupt
    """The wrapped MAIL message."""

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


def format_agent_address(
    agent_name: str, swarm_name: Optional[str] = None
) -> MAILAddress:
    """
    Format an agent address from agent name and optional swarm name.

    Returns:
        MAILAddress: Formatted address
    """
    if swarm_name:
        return MAILAddress(address_type="agent", address=f"{agent_name}@{swarm_name}")
    else:
        return MAILAddress(address_type="agent", address=agent_name)


def create_address(
    address: str, address_type: Literal["agent", "user", "system"]
) -> MAILAddress:
    """
    Create a MAILAddress object with the specified type.

    Args:
        address: The address string
        address_type: The type of address ("agent", "user", or "system")

    Returns:
        MAILAddress: A properly formatted address object
    """
    return MAILAddress(address_type=address_type, address=address)


def create_agent_address(address: str) -> MAILAddress:
    """Create a MAILAddress for an AI agent."""
    return create_address(address, "agent")


def create_user_address(address: str) -> MAILAddress:
    """Create a MAILAddress for a human user."""
    return create_address(address, "user")


def create_system_address(address: str) -> MAILAddress:
    """Create a MAILAddress for the system."""
    return create_address(address, "system")


def get_address_string(address: MAILAddress | str) -> str:
    """
    Extract the address string from either a MAILAddress object or a plain string.
    This provides backward compatibility during the transition.

    Args:
        address: Either a MAILAddress object or a plain string

    Returns:
        str: The address string
    """
    if isinstance(address, dict) and "address" in address:
        return address["address"]
    return str(address)


def get_address_type(address: MAILAddress | str) -> Literal["agent", "user", "system"]:
    """
    Extract the address type from either a MAILAddress object or a plain string.
    Defaults to "agent" for backward compatibility.

    Args:
        address: Either a MAILAddress object or a plain string

    Returns:
        Literal["agent", "user", "system"]: The address type
    """
    if isinstance(address, dict) and "address_type" in address:
        return address["address_type"]
    return "agent"  # Default assumption for backward compatibility


def build_body_xml(content: dict[str, Any]) -> str:
    """Build the XML representation a MAIL body section."""
    return str(dict2xml(content, wrap="body", indent=""))


def build_mail_xml(message: "MAILMessage") -> dict[str, str]:
    """Build the XML representation of a MAIL message."""
    to = (
        message["message"]["recipient"]  # type: ignore
        if "recipient" in message["message"]
        else message["message"]["recipients"]
    )

    # Extract sender and recipient information with type metadata
    sender = message["message"]["sender"]
    sender_str = get_address_string(sender)
    sender_type = get_address_type(sender)

    to_str = get_address_string(to) if isinstance(to, dict) else str(to)
    to_type = get_address_type(to) if isinstance(to, dict) else "agent"

    return {
        "role": "user",
        "content": f"""
<incoming_message>
<timestamp>{datetime.datetime.fromisoformat(message["timestamp"]).astimezone(datetime.timezone.utc).isoformat()}</timestamp>
<from type="{sender_type}">{sender_str}</from>
<to type="{to_type}">{to_str}</to>
<subject>{message["message"]["subject"]}</subject>
<body>{message["message"]["body"]}</body>
</incoming_message>
""",
    }


class MAILMessage(TypedDict):
    """A message using the MAIL protocol."""

    id: str
    """The unique identifier for the message."""

    timestamp: str
    """The timestamp of the message."""

    message: MAILRequest | MAILResponse | MAILBroadcast | MAILInterrupt
    """The message content."""

    msg_type: Literal[
        "request", "response", "broadcast", "interrupt", "broadcast_complete"
    ]
    """The type of the message."""
