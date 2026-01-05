# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Jacob Hahn

import datetime
from typing import Any, Literal, TypedDict

from dict2xml import dict2xml

MAIL_MESSAGE_TYPES = [
    "request",
    "response",
    "broadcast",
    "interrupt",
    "broadcast_complete",
]


class MAILAddress(TypedDict):
    """
    An address representing the sender or recipient of a MAIL message.
    """

    address_type: Literal["admin", "agent", "system", "user"]
    """The type of address."""
    address: str
    """The address of the sender or recipient."""


MAIL_ALL_LOCAL_AGENTS = MAILAddress(address_type="agent", address="all")


class MAILRequest(TypedDict):
    """
    A request to an agent using the MAIL protocol.
    """

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
    sender_swarm: str | None
    """The swarm name of the sender (for interswarm messages)."""
    recipient_swarm: str | None
    """The swarm name of the recipient (for interswarm messages)."""
    routing_info: dict[str, Any] | None
    """Additional routing information for interswarm messages."""


class MAILResponse(TypedDict):
    """
    A response from an agent using the MAIL protocol.
    """

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
    sender_swarm: str | None
    """The swarm name of the sender (for interswarm messages)."""
    recipient_swarm: str | None
    """The swarm name of the recipient (for interswarm messages)."""
    routing_info: dict[str, Any] | None
    """Additional routing information for interswarm messages."""


class MAILBroadcast(TypedDict):
    """
    A broadcast message using the MAIL protocol.
    """

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
    sender_swarm: str | None
    """The swarm name of the sender (for interswarm messages)."""
    recipient_swarms: list[str] | None
    """The swarm names of the recipients (for interswarm messages)."""
    routing_info: dict[str, Any] | None
    """Additional routing information for interswarm messages."""


class MAILInterrupt(TypedDict):
    """
    An interrupt using the MAIL protocol.
    """

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
    sender_swarm: str | None
    """The swarm name of the sender (for interswarm messages)."""
    recipient_swarms: list[str] | None
    """The swarm names of the recipients (for interswarm messages)."""
    routing_info: dict[str, Any] | None
    """Additional routing information for interswarm messages."""


class MAILInterswarmMessage(TypedDict):
    """
    An interswarm message wrapper for HTTP transport.
    """

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
    auth_token: str | None
    """Authentication token for interswarm communication."""
    task_owner: str
    """The owner of the task (role:id@swarm)."""
    task_contributors: list[str]
    """The contributors to the task (role:id@swarm)."""
    metadata: dict[str, Any] | None
    """Additional metadata for routing and processing."""


def parse_task_contributors(contributors: list[str]) -> list[tuple[str, str, str]]:
    """
    Parse a list of task contributors in the format `role:id@swarm`.
    """
    return [parse_task_contributor(contributor) for contributor in contributors]


def parse_task_contributor(contributor: str) -> tuple[str, str, str]:
    """
    Parse an individual task contributor in the format `role:id@swarm`.
    """
    if ":" not in contributor:
        raise ValueError("task contributor must be in the format 'role:id@swarm'")
    if "@" not in contributor:
        raise ValueError("task contributor must be in the format 'role:id@swarm'")

    role = contributor.split(":")[0]
    id = contributor.split(":")[1].split("@")[0]
    swarm = contributor.split("@")[1]

    return role, id, swarm


def parse_agent_address(address: str) -> tuple[str, str | None]:
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


def format_agent_address(agent_name: str, swarm_name: str | None = None) -> MAILAddress:
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
    address: str, address_type: Literal["admin", "agent", "system", "user"]
) -> MAILAddress:
    """
    Create a MAILAddress object with the specified type.

    Args:
        address: The address string
        address_type: The type of address ("admin", "agent", "system", or "user")

    Returns:
        MAILAddress: A properly formatted address object
    """
    return MAILAddress(address_type=address_type, address=address)


def create_admin_address(address: str) -> MAILAddress:
    """
    Create a MAILAddress for an admin.
    """
    return create_address(address, "admin")


def create_agent_address(address: str) -> MAILAddress:
    """
    Create a MAILAddress for an AI agent.
    """
    return create_address(address, "agent")


def create_system_address(address: str) -> MAILAddress:
    """
    Create a MAILAddress for the system.
    """
    return create_address(address, "system")


def create_user_address(address: str) -> MAILAddress:
    """
    Create a MAILAddress for a human user.
    """
    return create_address(address, "user")


def get_address_string(address: MAILAddress) -> str:
    """
    Extract the address string from a MAILAddress.
    """
    return address["address"]


def get_address_type(
    address: MAILAddress,
) -> Literal["admin", "agent", "system", "user"]:
    """
    Extract the address type from a MAILAddress.
    """
    return address["address_type"]


def build_body_xml(content: dict[str, Any]) -> str:
    """
    Build the XML representation a MAIL body section.
    """
    return str(dict2xml(content, wrap="body", indent=""))


def build_mail_xml(message: "MAILMessage", is_manual: bool = False) -> dict[str, str]:
    """
    Build the XML representation of a MAIL message.
    """
    if is_manual:
        return {
            "role": "user",
            "content": message["message"]["body"],
        }
    to = (
        message["message"]["recipient"]  # type: ignore
        if "recipient" in message["message"]
        else message["message"]["recipients"]
    )
    to = [to] if isinstance(to, dict) else to

    # Extract sender and recipient information with type metadata
    sender = message["message"]["sender"]
    sender_str = get_address_string(sender)
    sender_type = get_address_type(sender)
    return {
        "role": "user",
        "content": f"""
<incoming_message>
<timestamp>{datetime.datetime.fromisoformat(message["timestamp"]).astimezone(datetime.UTC).isoformat()}</timestamp>
<from type="{sender_type}">{sender_str}</from>
<to>
{[f'<address type="{get_address_type(recipient)}">{get_address_string(recipient)}</address>' for recipient in to]}
</to>
<subject>{message["message"]["subject"]}</subject>
<body>{message["message"]["body"]}</body>
</incoming_message>
""",
    }


def build_interswarm_mail_xml(message: MAILInterswarmMessage) -> dict[str, str]:
    """
    Build the XML representation of an interswarm MAIL message.
    """
    return {
        "role": "user",
        "content": f"""
<incoming_message>
<timestamp>{
            datetime.datetime.fromisoformat(message["timestamp"])
            .astimezone(datetime.UTC)
            .isoformat()
        }</timestamp>
<from type="agent">{message["payload"]["sender"]["address"]}</from>
<to>
{
            [
                f'<address type="agent">{recipient["address"]}</address>'
                for recipient in message["payload"]["recipients"]  # type: ignore
            ]
            if "recipients" in message["payload"]  # type: ignore
            else f'<address type="agent">{message["payload"]["recipient"]["address"]}</address>'
        }
</to>
<subject>{message["payload"]["subject"]}</subject>
<body>{message["payload"]["body"]}</body>
</incoming_message>
""",
    }


class MAILMessage(TypedDict):
    """
    A message using the MAIL protocol.
    """

    id: str
    """The unique identifier for the message."""
    timestamp: str
    """The timestamp of the message."""
    message: MAILRequest | MAILResponse | MAILBroadcast | MAILInterrupt
    """The message content."""
    msg_type: Literal[
        "request",
        "response",
        "broadcast",
        "interrupt",
        "broadcast_complete",
        "buffered",
    ]
    """The type of the message."""
