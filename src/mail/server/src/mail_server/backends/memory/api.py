# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import uuid
from datetime import UTC, datetime
from typing import Any

from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.messages import MAILMessage, MAILMessageSummary
from mail_protocol.core.outbox import MAILOutboxEntry, MAILOutboxEntrySummary
from mail_protocol.core.queues import MAILQueueEntry, MAILQueueEntrySummary
from mail_protocol.core.swarms import MAILSwarm, MAILSwarmSummary
from mail_protocol.core.trash import MAILTrashEntry, MAILTrashEntrySummary
from mail_protocol.core.user_agents import MAILAgent, MAILUserAgent
from mail_protocol.network.requests import (
    PostDaemonDeliverLocalRequest,
    PostDaemonDeliverRemoteRequest,
    PostDraftRequest,
    PostDraftSendRequest,
)

from mail_server.backends.base import MAILServerBackend


class MemoryBackend(MAILServerBackend):
    """
    A generic base class for the MAIL server backend.
    """

    #
    # Lifecyle handlers
    #
    async def on_server_startup(self, **kwargs: Any) -> None:
        """
        Handle backend events on server startup.
        """

        self.swarms: dict[str, MAILSwarm] = {}
        """
        A dict of all exposed MAIL swarms.
        Keys: swarm names
        Values: MAILSwarm instances
        """

        self.agents: dict[str, MAILAgent] = {}
        """
        A dict of all local MAIL agents.
        Keys: agent addresses
        Values: MAILAgent instances
        """

        self.messages: dict[str, MAILMessage] = {}
        """
        A dict of all MAIL messages known to this server.
        Keys: message IDs
        Values: MAILMessage instances
        """

        self.inbox_entries: dict[str, MAILInboxEntrySummary] = {}
        """
        A dict of all MAIL inbox entries on this server.
        Keys: message IDs
        Values: MAILInboxEntrySummary instances
        """

        self.inboxes: dict[str, list[str]] = {}
        """
        A dict of all local MAIL inboxes by user-agent.
        Keys: user-agent addresses
        Values: list of inbox entry message IDs
        """

        self.outbox_entries: dict[str, MAILOutboxEntrySummary] = {}
        """
        A dict of all MAIL outbox entries on this server.
        Keys: message IDs
        Values: MAILOutboxEntrySummary instances
        """

        self.outboxes: dict[str, list[str]] = {}
        """
        A dict of all local MAIL outboxes by user-agent.
        Keys: user-agent addresses
        Values: list of outbox entry message IDs
        """

        self.draft_entries: dict[str, MAILDraftsEntry] = {}
        """
        A dict of all MAIL draft entries on this server.
        Keys: draft IDs
        Values: MAILDraftsEntry instances
        """

        self.drafts: dict[str, list[str]] = {}
        """
        A dict of all local MAIL draft boxes by user-agent.
        Keys: user-agent addresses
        Values: list of draft entry draft IDs
        """

        self.trash_entries: dict[str, MAILTrashEntry] = {}
        """
        A dict of all MAIL trash entries on this server.
        Keys: message IDs
        Values: MAILTrashEntry instances
        """

        self.trashes: dict[str, list[str]] = {}
        """
        A dict of all local MAIL trash boxes by user-agent.
        Keys: user-agent addresses
        Values: list of trash entry message IDs
        """

        self.delivery_queue: dict[str, MAILQueueEntrySummary] = {}
        """
        A dict of all MAIL messages in the delivery queue.
        Keys: message IDs
        Values: MAILQueueEntrySummary instances
        """

    async def on_server_shutdown(self, **kwargs: Any) -> None:
        """
        Handle backend events on server shutdown.
        """

        pass

    #
    # Swarm endpoint handlers
    #
    async def get_swarms(self) -> list[MAILSwarmSummary]:
        """
        Get all swarms exposed by this server.
        """

        swarm_summaries = [swarm.summarize() for swarm in self.swarms.values()]
        return swarm_summaries

    async def get_swarm(self, swarm_name: str) -> MAILSwarm:
        """
        Get a specific exposed swarm by name.
        """

        swarm = self.swarms.get(swarm_name)
        if swarm is None:
            raise ValueError(f"swarm with name {swarm_name} not found")

        return swarm

    async def get_swarm_health(self, swarm_name: str) -> str:
        """
        Get the current swarm health status message.
        """

        swarm = self.swarms.get(swarm_name)
        if swarm is None:
            raise ValueError(f"swarm with name {swarm_name} not found")

        return "ok"

    #
    # Inbox endpoint handlers
    #
    async def get_inbox(self, user_agent: MAILUserAgent) -> list[MAILInboxEntrySummary]:
        """
        Get the user-agent's inbox.
        """

        ua_address = user_agent.get_address()
        inbox_msg_ids = self.inboxes.get(ua_address)
        if inbox_msg_ids is None:
            raise ValueError(f"no inbox found for address {ua_address}")

        inbox_entries: list[MAILInboxEntrySummary] = []
        for msg_id in inbox_msg_ids:
            inbox_entry = self.inbox_entries.get(msg_id)
            if inbox_entry is None:
                raise ValueError(f"no inbox entry found for message ID {msg_id}")
            inbox_entries.append(inbox_entry)

        return inbox_entries

    async def get_inbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILInboxEntry:
        """
        Get a specific message by ID in the user-agent's inbox.
        """

        ua_address = user_agent.get_address()
        inbox_msg_ids = self.inboxes.get(ua_address)
        if inbox_msg_ids is None:
            raise ValueError(f"no inbox found for address {ua_address}")
        if message_id not in inbox_msg_ids:
            raise ValueError(
                f"message with ID {message_id} not found in inbox at address {ua_address}"
            )

        inbox_entry = self.inbox_entries.get(message_id)
        if inbox_entry is None:
            raise ValueError(f"message with ID {message_id} not found in inbox entries")
        message = self.messages.get(message_id)
        if message is None:
            raise ValueError(f"message with ID {message_id} not found in messages")

        return MAILInboxEntry(
            message=message,
            received_at=inbox_entry.received_at,
            opened=inbox_entry.opened,
        )

    async def delete_inbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILInboxEntry:
        """
        Move a specific message by ID to the user-agent's trash.
        """

        raise NotImplementedError

    #
    # Outbox endpoint handlers
    #
    async def get_outbox(
        self, user_agent: MAILUserAgent
    ) -> list[MAILOutboxEntrySummary]:
        """
        Get the user-agent's outbox.
        """

        ua_address = user_agent.get_address()
        outbox_msg_ids = self.outboxes.get(ua_address)
        if outbox_msg_ids is None:
            raise ValueError(f"no outbox found for address {ua_address}")

        outbox_entries: list[MAILOutboxEntrySummary] = []
        for msg_id in outbox_msg_ids:
            outbox_entry = self.outbox_entries.get(msg_id)
            if outbox_entry is None:
                raise ValueError(f"no outbox entry found for message ID {msg_id}")
            outbox_entries.append(outbox_entry)

        return outbox_entries

    async def get_outbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILOutboxEntry:
        """
        Get a specific message by ID in the user-agent's outbox.
        """

        ua_address = user_agent.get_address()
        outbox_msg_ids = self.outboxes.get(ua_address)
        if outbox_msg_ids is None:
            raise ValueError(f"no outbox found for address {ua_address}")
        if message_id not in outbox_msg_ids:
            raise ValueError(
                f"message with ID {message_id} not found in outbox at address {ua_address}"
            )

        outbox_entry = self.outbox_entries.get(message_id)
        if outbox_entry is None:
            raise ValueError(
                f"message with ID {message_id} not found in outbox entries"
            )
        message = self.messages.get(message_id)
        if message is None:
            raise ValueError(f"message with ID {message_id} not found in messages")

        return MAILOutboxEntry(
            message=message,
            delivered_at=outbox_entry.delivered_at,
        )

    #
    # Drafts box endpoints
    #
    async def get_drafts(
        self, user_agent: MAILUserAgent
    ) -> list[MAILDraftsEntrySummary]:
        """
        Get the user-agent's draft box.
        """

        ua_address = user_agent.get_address()
        draft_ids = self.drafts.get(ua_address)
        if draft_ids is None:
            raise ValueError(f"no drafts box found for address {ua_address}")

        draft_entries: list[MAILDraftsEntrySummary] = []
        for draft_id in draft_ids:
            draft_entry = self.draft_entries.get(draft_id)
            if draft_entry is None:
                raise ValueError(f"draft with ID {draft_id} not found in draft entries")
            draft_entries.append(draft_entry.summarize())

        return draft_entries

    async def post_draft(
        self,
        user_agent: MAILUserAgent,
        payload: PostDraftRequest,
    ) -> MAILDraftsEntry:
        """
        Post a new draft for this user-agent.
        """

        ua_address = user_agent.get_address()
        draft_ids = self.drafts.get(ua_address)
        if draft_ids is None:
            raise ValueError(f"no drafts box found for address {ua_address}")

        draft_id = str(uuid.uuid4())
        draft = MAILDraft(
            draft_id=draft_id,
            subject=payload.subject,
            body=payload.body,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        draft_entry = MAILDraftsEntry(draft=draft, sent_at=datetime.now(UTC))

        self.draft_entries.update({draft_id: draft_entry})
        self.drafts[ua_address].append(draft_id)

        return draft_entry

    async def get_draft(
        self, user_agent: MAILUserAgent, draft_id: str
    ) -> MAILDraftsEntry:
        """
        Get a specific message draft by ID for this user-agent.
        """

        ua_address = user_agent.get_address()
        draft_ids = self.drafts.get(ua_address)
        if draft_ids is None:
            raise ValueError(f"no drafts box found for address {ua_address}")
        if draft_id not in draft_ids:
            raise ValueError(
                f"draft with ID {draft_id} not found in draft box at address {ua_address}"
            )

        draft_entry = self.draft_entries.get(draft_id)
        if draft_entry is None:
            raise ValueError(f"draft with ID {draft_id} not found in draft box entries")

        return draft_entry

    async def delete_draft(
        self, user_agent: MAILUserAgent, draft_id: str
    ) -> MAILDraftsEntry:
        """
        Delete an existing message draft by ID for this user-agent.
        """

        raise NotImplementedError

    async def send_draft(
        self,
        user_agent: MAILUserAgent,
        draft_id: str,
        payload: PostDraftSendRequest,
    ) -> MAILMessage:
        """
        Create a MAIL message from an existing user-agent draft and send.
        """

        ua_address = user_agent.get_address()
        draft_ids = self.drafts.get(ua_address)
        if draft_ids is None:
            raise ValueError(f"no drafts box found for address {ua_address}")
        if draft_id not in draft_ids:
            raise ValueError(
                f"draft with ID {draft_id} not found in draft box at address {ua_address}"
            )

        draft_entry = self.draft_entries.get(draft_id)
        if draft_entry is None:
            raise ValueError(f"draft with ID {draft_id} not found in draft box entries")
        draft = draft_entry.draft

        message = MAILMessage(
            message_id=draft_id,
            sender=ua_address,
            recipients=payload.recipients,
            subject=draft.subject,
            body=draft.body,
            sent_at=datetime.now(UTC),
            metadata={},
        )
        self.messages.update({message.message_id: message})

        queue_entry = MAILQueueEntry(
            message=message,
            queued_at=datetime.now(UTC),
        )
        self.delivery_queue.update({message.message_id: queue_entry.summarize()})

        return message

    #
    # Trash box endpoints
    #
    async def get_trash(self, user_agent: MAILUserAgent) -> list[MAILTrashEntrySummary]:
        """
        Get a list of messages in the user-agent's trash box.
        """

        ua_address = user_agent.get_address()
        trash_msg_ids = self.trashes.get(ua_address)
        if trash_msg_ids is None:
            raise ValueError(f"no trash box found for address {ua_address}")

        trash_entries: list[MAILTrashEntrySummary] = []
        for msg_id in trash_msg_ids:
            trash_entry = self.trash_entries.get(msg_id)
            if trash_entry is None:
                raise ValueError(f"message with ID {msg_id} not found in trash entries")
            trash_entries.append(trash_entry.summarize())

        return trash_entries

    async def get_trash_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILTrashEntry:
        """
        Get a specific trashed message by ID for this user-agent.
        """

        ua_address = user_agent.get_address()
        trash_msg_ids = self.drafts.get(ua_address)
        if trash_msg_ids is None:
            raise ValueError(f"no trash box found for address {ua_address}")
        if message_id not in trash_msg_ids:
            raise ValueError(
                f"message with ID {message_id} not found in trash box at address {ua_address}"
            )

        trash_entry = self.trash_entries.get(message_id)
        if trash_entry is None:
            raise ValueError(f"message with ID {message_id} not found in trash entries")

        return trash_entry

    async def delete_trash_message(
        self,
        user_agent: MAILUserAgent,
        message_id: str,
    ) -> MAILTrashEntry:
        """
        Delete a specific trashed message by ID for this user-agent.
        """

        raise NotImplementedError

    async def clear_trash(
        self, user_agent: MAILUserAgent
    ) -> list[MAILTrashEntrySummary]:
        """
        Delete all existing contents from this user-agent's trash box.
        """

        raise NotImplementedError

    #
    # Daemon-only endpoints
    #
    async def get_daemon_queue(
        self, user_agent: MAILUserAgent
    ) -> list[MAILQueueEntrySummary]:
        """
        Get the current message delivery queue.
        """

        raise NotImplementedError

    async def get_daemon_queue_entry(
        self,
        user_agent: MAILUserAgent,
        message_id: str,
    ) -> MAILQueueEntry:
        """
        Get a specific queued message by ID.
        """

        raise NotImplementedError

    async def daemon_deliver_local(
        self,
        user_agent: MAILUserAgent,
        payload: PostDaemonDeliverLocalRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by other local agents.
        """

        raise NotImplementedError

    async def daemon_deliver_remote(
        self,
        user_agent: MAILUserAgent,
        payload: PostDaemonDeliverRemoteRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by remote agents.
        """

        raise NotImplementedError
