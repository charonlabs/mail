# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import asyncio
import hashlib
import hmac
import logging
import time
from abc import abstractmethod
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import httpx
from mail_protocol.core.drafts import MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.lists import MAILListInBackend
from mail_protocol.core.messages import MAILMessage, MAILMessageSummary
from mail_protocol.core.outbox import MAILOutboxEntry, MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm, MAILSwarmSummary
from mail_protocol.core.trash import MAILTrashEntry, MAILTrashEntrySummary
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
    MAILUserAgentInBackend,
)
from mail_protocol.core.webhooks import MAILMessageInWebhook, MAILWebhook
from mail_protocol.network.requests import (
    AdminAgentPostRequest,
    AdminDaemonPostRequest,
    AdminListPatchRequest,
    AdminListPostRequest,
    AdminSwarmPostRequest,
    AdminUserPostRequest,
    AdminWebhooksPatchRequest,
    AdminWebhooksPostRequest,
    AuthPasswordResetRequest,
    DaemonDeliverLocalRequest,
    DaemonDeliverRemoteRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)
from mail_protocol.network.responses import AdminWebhooksDeleteResponse
from mail_protocol.network.webhooks import WebhookDeliveredPostRequest

logger = logging.getLogger(__name__)


class MAILServerBackend(Protocol):
    """
    A generic base class for the MAIL server backend.
    """

    client = httpx.AsyncClient(
        headers={
            "User-Agent": "Multi-Agent-Interface-Layer-Server/2.0.0 (github.com/charonlabs/mail)"
        }
    )

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

    @abstractmethod
    async def reset_password(
        self, user_agent: MAILUserAgent, payload: AuthPasswordResetRequest
    ) -> str:
        """
        Reset the password for an authenticated user-agent.
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
        payload: DraftPostRequest,
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
        payload: DraftSendPostRequest,
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
    async def daemon_clear_message_buffer(
        self,
        daemon: MAILDaemon,
    ) -> list[str]:
        """
        Obtain all messages by ID to be delivered on the server and clear the buffer.
        """

        pass

    @abstractmethod
    async def daemon_deliver_local(
        self,
        daemon: MAILDaemon,
        payload: DaemonDeliverLocalRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by other local agents.
        """

        pass

    @abstractmethod
    async def daemon_deliver_remote(
        self,
        daemon: MAILDaemon,
        payload: DaemonDeliverRemoteRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by remote agents.
        """

        pass

    #
    # Admin-only endpoints
    #
    @abstractmethod
    async def admin_get_agents(
        self,
        admin: MAILAdmin,
    ) -> list[str]:
        """
        Get a list of agents by local address (agent@swarm) registered on this server.
        """

        pass

    @abstractmethod
    async def admin_get_agent(
        self,
        admin: MAILAdmin,
        agent_address: str,
    ) -> MAILAgent:
        """
        Get a specific registered agent by local address (agent@swarm).
        """

        pass

    @abstractmethod
    async def admin_post_agent(
        self,
        admin: MAILAdmin,
        payload: AdminAgentPostRequest,
    ) -> MAILAgent:
        """
        Create a new MAIL agent with the specified credentials.
        """

        pass

    @abstractmethod
    async def admin_delete_agent(
        self,
        admin: MAILAdmin,
        agent_address: str,
    ) -> MAILAgent:
        """
        Delete an existing MAIL agent by local address (agent@swarm).
        """

        pass

    @abstractmethod
    async def admin_get_daemons(
        self,
        admin: MAILAdmin,
    ) -> list[str]:
        """
        Get a list of daemons by worker name registered on this server.
        """

        pass

    @abstractmethod
    async def admin_get_daemon(
        self,
        admin: MAILAdmin,
        worker_name: str,
    ) -> MAILDaemon:
        """
        Get a specific registered daemon by worker name.
        """

        pass

    @abstractmethod
    async def admin_post_daemon(
        self,
        admin: MAILAdmin,
        payload: AdminDaemonPostRequest,
    ) -> MAILDaemon:
        """
        Cerate a new MAIL daemon with the specified credentials.
        """

        pass

    @abstractmethod
    async def admin_delete_daemon(
        self,
        admin: MAILAdmin,
        worker_name: str,
    ) -> MAILDaemon:
        """
        Delete an existing MAIL daemon by worker name.
        """

        pass

    @abstractmethod
    async def admin_get_users(
        self,
        admin: MAILAdmin,
    ) -> list[str]:
        """
        Get a list of users by user ID registered on this server.
        """

        pass

    @abstractmethod
    async def admin_get_user(
        self,
        admin: MAILAdmin,
        user_id: str,
    ) -> MAILUser:
        """
        Get a specific registered user by user ID.
        """

        pass

    @abstractmethod
    async def admin_post_user(
        self,
        admin: MAILAdmin,
        payload: AdminUserPostRequest,
    ) -> MAILUser:
        """
        Create a new MAIL user with the specified credentials.
        """

        pass

    @abstractmethod
    async def admin_delete_user(
        self,
        admin: MAILAdmin,
        user_id: str,
    ) -> MAILUser:
        """
        Delete an existing MAIL user by user ID.
        """

        pass

    @abstractmethod
    async def admin_post_swarm(
        self,
        admin: MAILAdmin,
        payload: AdminSwarmPostRequest,
    ) -> MAILSwarm:
        """
        Create a new MAIL swarm on this server.
        """

        pass

    @abstractmethod
    async def admin_delete_swarm(
        self,
        admin: MAILAdmin,
        swarm_name: str,
    ) -> MAILSwarm:
        """
        Delete an existing MAIL swarm on this server by name.
        """

        pass

    #
    #
    # Webhook handlers
    #
    @abstractmethod
    async def admin_webhooks_get(self, admin: MAILAdmin) -> list[str]:
        """
        Get the IDs for all existing server webhooks.
        """

        pass

    @abstractmethod
    async def admin_webhook_get(self, admin: MAILAdmin, webhook_id: str) -> MAILWebhook:
        """
        Get an existing server webhook by ID.
        """

        pass

    @abstractmethod
    async def admin_webhook_post(
        self,
        admin: MAILAdmin,
        payload: AdminWebhooksPostRequest,
    ) -> MAILWebhook:
        """
        Create a new server webhook.
        """

        pass

    @abstractmethod
    async def admin_webhook_patch(
        self,
        admin: MAILAdmin,
        webhook_id: str,
        payload: AdminWebhooksPatchRequest,
    ) -> MAILWebhook:
        """
        Update an existing server webhook URL and/or secret.
        """

        pass

    @abstractmethod
    async def admin_webhook_delete(
        self,
        admin: MAILAdmin,
        webhook_id: str,
    ) -> MAILWebhook:
        """
        Delete an existing server webhook by ID.
        """

        pass

    async def handle_webhook_delivered_for_url(
        self,
        url: str,
        recipient: str,
        message: MAILMessage,
        secret: str,
    ) -> None:
        """
        Common webhook `mail.delivered` handler for MAIL server backends.
        """

        event_id = f"evt_{uuid4()}"
        if not self._webhook_delivered_post(
            event_id=event_id,
            url=url,
            recipient=recipient,
            message=message,
            secret=secret,
        ):
            return

        await asyncio.sleep(1)
        if not self._webhook_delivered_post(
            event_id=event_id,
            url=url,
            recipient=recipient,
            message=message,
            secret=secret,
        ):
            return

        await asyncio.sleep(30)
        if not self._webhook_delivered_post(
            event_id=event_id,
            url=url,
            recipient=recipient,
            message=message,
            secret=secret,
        ):
            return

        await asyncio.sleep(300)
        if not self._webhook_delivered_post(
            event_id=event_id,
            url=url,
            recipient=recipient,
            message=message,
            secret=secret,
        ):
            return

        await asyncio.sleep(3600)
        if not self._webhook_delivered_post(
            event_id=event_id,
            url=url,
            recipient=recipient,
            message=message,
            secret=secret,
        ):
            return

        await asyncio.sleep(6 * 3600)
        if not self._webhook_delivered_post(
            event_id=event_id,
            url=url,
            recipient=recipient,
            message=message,
            secret=secret,
        ):
            return

        logger.warning(
            f"webhook POST request for `mail.delivered` to {url} failed after 5 tries"
        )

    async def _webhook_delivered_post(
        self,
        event_id: str,
        url: str,
        recipient: str,
        message: MAILMessage,
        secret: str,
    ) -> bool:
        """
        Attempt an individual POST request fo the webhook `mail.delivered` for a specific URL.
        Return True if a retry is needed, False otherwise.
        """

        delivered_at = datetime.now(UTC)
        payload = WebhookDeliveredPostRequest(
            event="mail.delivered",
            event_id=event_id,
            delivered_at=delivered_at,
            message=MAILMessageInWebhook(
                message_id=message.message_id,
                sender=message.sender,
                recipient=recipient,
                subject=message.subject,
                body=message.body,
                sent_at=message.sent_at,
                swarm=recipient.split("@")[1],
                metadata={},
            ),
        )
        raw_body = payload.model_dump_json()
        signature = hmac.new(
            key=secret.encode(),
            msg=f"{delivered_at}.{raw_body}".encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        async with self.client as client:
            try:
                response = await client.post(
                    url=url,
                    headers={
                        "Content-Type": "application/json",
                        "X-MAIL-Event-Id": payload.event_id,
                        "X-MAIL-Timestamp": f"{int(time.time())}",
                        "X-MAIL-Signature": f"sha256={signature}",
                    },
                    json=payload,
                    timeout=10,
                )
            except httpx.TimeoutException:
                return True

        # successful response
        if (response.status_code >= 200) and (response.status_code < 300):
            return False
        # 4xx
        elif (response.status_code >= 400) and (response.status_code < 500):
            if response.status_code == 429:
                return True
            return False
        # 5xx
        elif (response.status_code >= 500) and (response.status_code < 600):
            return True

        return False

    #
    # List endpoints
    #
    @abstractmethod
    async def get_lists(self) -> list[MAILListInBackend]:
        """
        Get all MAIL lists known to this server (no auth scope).
        """

        pass

    @abstractmethod
    async def get_list(self, list_address: str) -> MAILListInBackend:
        """
        Get a specific MAIL list by address (no auth scope).
        """

        pass

    @abstractmethod
    async def admin_get_lists(
        self,
        admin: MAILAdmin,
    ) -> list[MAILListInBackend]:
        """
        Admin read of every list known to the server.
        """

        pass

    @abstractmethod
    async def admin_get_list(
        self,
        admin: MAILAdmin,
        list_address: str,
    ) -> MAILListInBackend:
        """
        Admin read of a specific MAIL list.
        """

        pass

    @abstractmethod
    async def admin_post_list(
        self,
        admin: MAILAdmin,
        payload: AdminListPostRequest,
    ) -> MAILListInBackend:
        """
        Create a new MAIL list on this server.
        """

        pass

    @abstractmethod
    async def admin_patch_list(
        self,
        admin: MAILAdmin,
        list_address: str,
        payload: AdminListPatchRequest,
    ) -> MAILListInBackend:
        """
        Update mutable fields on an existing MAIL list. v1 only allows
        policy edits; the canonical address (name, swarm, host) is
        immutable for the life of the list.
        """

        pass

    @abstractmethod
    async def admin_delete_list(
        self,
        admin: MAILAdmin,
        list_address: str,
    ) -> MAILListInBackend:
        """
        Delete an existing MAIL list by its full ``list:`` address.
        """

        pass

    @abstractmethod
    async def add_list_member(
        self,
        list_address: str,
        member_address: str,
    ) -> MAILListInBackend:
        """
        Append a member to a MAIL list. Idempotent.

        Permission checks (against the list's ``join_policy``) are the
        responsibility of the calling router; the storage layer does not
        enforce them.
        """

        pass

    @abstractmethod
    async def remove_list_member(
        self,
        list_address: str,
        member_address: str,
    ) -> MAILListInBackend:
        """
        Remove a member from a MAIL list. Idempotent.
        """

        pass
