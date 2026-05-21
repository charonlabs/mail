# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from mail_protocol.core.drafts import MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.queues import MAILQueueEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILAgent, MAILUserAgentInBackend


#
# Load memory backend from the local filesystem
# (on server startup)
#
async def load_user_agents() -> dict[str, MAILUserAgentInBackend]:
    """
    Load saved user-agents from the local filesystem.
    """

    raise NotImplementedError


async def load_swarms() -> dict[str, MAILSwarm]:
    """
    Load saved MAIL swarms from the local filesystem.
    """

    raise NotImplementedError


async def load_agents() -> dict[str, MAILAgent]:
    """
    Load saved MAIL agents from the local filesystem.
    """

    raise NotImplementedError


async def load_messages() -> dict[str, MAILMessage]:
    """
    Load saved MAIL messages from the local filesystem.
    """

    raise NotImplementedError


async def load_inbox_entries() -> dict[str, MAILInboxEntrySummary]:
    """
    Load saved inbox entries from the local filesystem.
    """

    raise NotImplementedError


async def load_inboxes() -> dict[str, list[str]]:
    """
    Load saved user-agent inboxes from the local filesystem.
    """

    raise NotImplementedError


async def load_outbox_entries() -> dict[str, MAILOutboxEntrySummary]:
    """
    Load saved outbox entries from the local filesystem.
    """

    raise NotImplementedError


async def load_outboxes() -> dict[str, list[str]]:
    """
    Load saved user-agent outboxes from the local filesystem.
    """

    raise NotImplementedError


async def load_draft_entries() -> dict[str, MAILDraftsEntry]:
    """
    Load saved draft box entries from the local filesystem.
    """

    raise NotImplementedError


async def load_drafts() -> dict[str, list[str]]:
    """
    Load saved user-agent draft boxes from the local filesystem.
    """

    raise NotImplementedError


async def load_trash_entries() -> dict[str, MAILTrashEntry]:
    """
    Load saved trash box entries from the local filesystem.
    """

    raise NotImplementedError


async def load_trashes() -> dict[str, list[str]]:
    """
    Load saved user-agent trash boxes from the local filesystem.
    """

    raise NotImplementedError


async def load_delivery_queue() -> dict[str, MAILQueueEntrySummary]:
    """
    Load saved message delivery queue from the local filesystem.
    """

    raise NotImplementedError


#
# Save memory backend to the local filesystem
# (on server shutdown)
#
async def save_user_agents(user_agents: dict[str, MAILUserAgentInBackend]) -> None:
    """
    Save user-agents from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_swarms(swarms: dict[str, MAILSwarm]) -> None:
    """
    Save MAIL swarms from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_agents(agents: dict[str, MAILAgent]) -> None:
    """
    Save MAIL agents from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_messages(messages: dict[str, MAILMessage]) -> None:
    """
    Save MAIL messages from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_inbox_entries(inbox_entries: dict[str, MAILInboxEntrySummary]) -> None:
    """
    Save inbox entries from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_inboxes(inboxes: dict[str, list[str]]) -> None:
    """
    Save user-agent inboxes from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_outbox_entries(
    outbox_entries: dict[str, MAILOutboxEntrySummary],
) -> None:
    """
    Save outbox entries from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_outboxes(outboxes: dict[str, list[str]]) -> None:
    """
    Save user-agent outboxes from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_draft_entries(
    draft_entries: dict[str, MAILDraftsEntry],
) -> None:
    """
    Save draft entries from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_drafts(drafts: dict[str, list[str]]) -> None:
    """
    Save user-agent draft boxes from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_trash_entries(trash_entries: dict[str, MAILTrashEntry]) -> None:
    """
    Save trash entries from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_trashes(trashes: dict[str, list[str]]) -> None:
    """
    Save user-agent trash boxes from memory to the local filesystem.
    """

    raise NotImplementedError


async def save_delivery_queue(delivery_queue: dict[str, MAILQueueEntrySummary]) -> None:
    """
    Save message delivery queue from memory to the local filesystem.
    """

    raise NotImplementedError
