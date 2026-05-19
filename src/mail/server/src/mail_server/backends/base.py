# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from abc import abstractmethod
from typing import Any, Protocol

from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm, MAILSwarmSummary
from mail_protocol.core.user_agents import MAILUserAgent


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
