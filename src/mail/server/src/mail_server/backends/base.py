# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from abc import abstractmethod
from typing import Any, Protocol

from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.messages import MAILMessage, MAILMessageSummary
from mail_protocol.core.outbox import MAILOutboxEntry, MAILOutboxEntrySummary
from mail_protocol.core.queues import MAILQueueEntry, MAILQueueEntrySummary
from mail_protocol.core.swarms import MAILSwarm, MAILSwarmSummary
from mail_protocol.core.trash import MAILTrashEntry, MAILTrashEntrySummary
from mail_protocol.core.user_agents import MAILUserAgent, MAILUserAgentInBackend
from mail_protocol.network.requests import (
    PostDaemonDeliverLocalRequest,
    PostDaemonDeliverRemoteRequest,
    PostDraftRequest,
    PostDraftSendRequest,
)


class MAILServerBackend(Protocol):
    """
    A generic base class for the MAIL server backend.
    """

    #
    # Lifecyle handlers
    #
    @abstractmethod
    async def on_server_startup(self, **kwargs: Any) -> None:
        """
        Handle backend events on server startup.
        """

        pass

    @abstractmethod
    async def on_server_shutdown(self, **kwargs: Any) -> None:
        """
        Handle backend events on server shutdown.
        """

        pass

    #
    # User-agent handlers
    #
    @abstractmethod
    async def get_user_agent(self, address: str) -> MAILUserAgentInBackend:
        """
        Get the existing user-agent by MAIL address in the server backend.
        """

        pass

    @abstractmethod
    async def user_agent_exists(self, address: str) -> bool:
        """
        Return True if the user-agent exists in the backend, otherwise False.
        """

        pass

    #
    # Swarm endpoint handlers
    #
    @abstractmethod
    async def get_swarms(self) -> list[MAILSwarmSummary]:
        """
        Get all swarms exposed by this server.
        """

        pass

    @abstractmethod
    async def get_swarm(self, swarm_name: str) -> MAILSwarm:
        """
        Get a specific exposed swarm by name.
        """

        pass

    @abstractmethod
    async def get_swarm_health(self, swarm_name: str) -> str:
        """
        Get the current swarm health status message.
        """

        pass

    #
    # Inbox endpoint handlers
    #
    @abstractmethod
    async def get_inbox(self, user_agent: MAILUserAgent) -> list[MAILInboxEntrySummary]:
        """
        Get the user-agent's inbox.
        """

        pass

    @abstractmethod
    async def get_inbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILInboxEntry:
        """
        Get a specific message by ID in the user-agent's inbox.
        """

        pass

    @abstractmethod
    async def delete_inbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILInboxEntry:
        """
        Move a specific message by ID to the user-agent's trash.
        """

        pass

    #
    # Outbox endpoint handlers
    #
    @abstractmethod
    async def get_outbox(
        self, user_agent: MAILUserAgent
    ) -> list[MAILOutboxEntrySummary]:
        """
        Get the user-agent's outbox.
        """

        pass

    @abstractmethod
    async def get_outbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILOutboxEntry:
        """
        Get a specific message by ID in the user-agent's outbox.
        """

        pass

    #
    # Drafts box endpoints
    #
    @abstractmethod
    async def get_drafts(
        self, user_agent: MAILUserAgent
    ) -> list[MAILDraftsEntrySummary]:
        """
        Get the user-agent's draft box.
        """

        pass

    @abstractmethod
    async def post_draft(
        self,
        user_agent: MAILUserAgent,
        payload: PostDraftRequest,
    ) -> MAILDraftsEntry:
        """
        Post a new draft for this user-agent.
        """

        pass

    @abstractmethod
    async def get_draft(
        self, user_agent: MAILUserAgent, draft_id: str
    ) -> MAILDraftsEntry:
        """
        Get a specific message draft by ID for this user-agent.
        """

        pass

    @abstractmethod
    async def delete_draft(
        self, user_agent: MAILUserAgent, draft_id: str
    ) -> MAILDraftsEntry:
        """
        Delete an existing message draft by ID for this user-agent.
        """

        pass

    @abstractmethod
    async def send_draft(
        self,
        user_agent: MAILUserAgent,
        draft_id: str,
        payload: PostDraftSendRequest,
    ) -> MAILMessage:
        """
        Create a MAIL message from an existing user-agent draft and send.
        """

        pass

    #
    # Trash box endpoints
    #
    @abstractmethod
    async def get_trash(self, user_agent: MAILUserAgent) -> list[MAILTrashEntrySummary]:
        """
        Get a list of messages in the user-agent's trash box.
        """

        pass

    @abstractmethod
    async def get_trash_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILTrashEntry:
        """
        Get a specific trashed message by ID for this user-agent.
        """

        pass

    @abstractmethod
    async def delete_trash_message(
        self,
        user_agent: MAILUserAgent,
        message_id: str,
    ) -> MAILTrashEntry:
        """
        Delete a specific trashed message by ID for this user-agent.
        """

        pass

    @abstractmethod
    async def clear_trash(
        self, user_agent: MAILUserAgent
    ) -> list[MAILTrashEntrySummary]:
        """
        Delete all existing contents from this user-agent's trash box.
        """

        pass

    #
    # Daemon-only endpoints
    #
    @abstractmethod
    async def get_daemon_queue(
        self, user_agent: MAILUserAgent
    ) -> list[MAILQueueEntrySummary]:
        """
        Get the current message delivery queue.
        """

        pass

    @abstractmethod
    async def get_daemon_queue_entry(
        self,
        user_agent: MAILUserAgent,
        message_id: str,
    ) -> MAILQueueEntry:
        """
        Get a specific queued message by ID.
        """

        pass

    @abstractmethod
    async def daemon_deliver_local(
        self,
        user_agent: MAILUserAgent,
        payload: PostDaemonDeliverLocalRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by other local agents.
        """

        pass

    @abstractmethod
    async def daemon_deliver_remote(
        self,
        user_agent: MAILUserAgent,
        payload: PostDaemonDeliverRemoteRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by remote agents.
        """

        pass
