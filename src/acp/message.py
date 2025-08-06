from datetime import datetime
from typing import Any, Literal, TypedDict

from dict2xml import dict2xml


class ACPRequest(TypedDict):
    """A request to an agent using the ACP protocol."""

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


class ACPResponse(TypedDict):
    """A response from an agent using the ACP protocol."""

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


class ACPBroadcast(TypedDict):
    """A broadcast message using the ACP protocol."""

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


class ACPInterrupt(TypedDict):
    """An interrupt using the ACP protocol."""

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


def build_sme_context_xml(sections: list[dict[str, str]]) -> str:
    """Build XML for SME context sections following the SME prompt schema.

    Args:
        sections: List of dictionaries with 'SECTION_TITLE' and 'SECTION_CONTENT' keys

    Returns:
        XML string formatted for SME context with numbered sections
    """
    xml = ""
    for i, section in enumerate(sections, 1):
        xml += f"<CONTEXT>\n"
        xml += f"[{i}]\n"
        xml += f"<SECTION_TITLE>\n"
        xml += f"{section['SECTION_TITLE']}\n"
        xml += f"</SECTION_TITLE>\n"
        xml += f"<SECTION_CONTENT>\n"
        xml += f"{section['SECTION_CONTENT']}\n"
        xml += f"</SECTION_CONTENT>\n"
        xml += f"</CONTEXT>\n"
        if i < len(sections):
            xml += "\n"
    return xml


def build_sme_task_xml(title: str, description: str) -> str:
    """Build XML for SME task following the SME prompt schema.

    Args:
        title: The task title
        description: The task description

    Returns:
        XML string formatted for SME task
    """
    xml = f"<TASK>\n"
    xml += f"<TASK_TITLE>\n"
    xml += f"{title}\n"
    xml += f"</TASK_TITLE>\n"
    xml += f"<TASK_DESCRIPTION>\n"
    xml += f"{description}\n"
    xml += f"</TASK_DESCRIPTION>\n"
    xml += f"</TASK>\n"
    return xml


class ACPMessage(TypedDict):
    """A message using the ACP protocol."""

    id: str
    """The unique identifier for the message."""

    timestamp: datetime
    """The timestamp of the message."""

    message: ACPRequest | ACPResponse | ACPBroadcast | ACPInterrupt
    """The message content."""

    msg_type: Literal[
        "request", "response", "broadcast", "interrupt", "broadcast_complete"
    ]
    """The type of the message."""
