# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
``SQLiteBackend`` — a durable, transactional ``MAILServerBackend``.

Each protocol method opens one ``Database.session()`` and delegates to the
repository layer; the session context manager owns the transaction, so
multi-write operations (``send_draft``, daemon delivery, inbox→trash moves)
commit atomically. Error semantics mirror the memory backend exactly — the same
human-readable ``ValueError`` messages the routers translate to HTTP errors and
the integration suite asserts on.

Two deliberate refinements over the memory backend, both enabled by lazy
membership rows (no per-agent box dicts to pre-create):

- Box reads treat "no membership rows" as an *empty box for a known agent*
  rather than raising "no inbox found"; the agent is already authenticated.
- Delivery is idempotent per (owner, box, message): re-delivering the same
  message to a recipient is a no-op instead of a duplicate row.

Webhooks fire *after* the delivery transaction commits (never inside it), via
``asyncio.create_task`` — matching memory and keeping DB transactions short.

The gap-fill methods (``delete_inbox_message``, ``delete_draft``,
``delete_trash_message``, ``clear_trash``, ``admin_webhook_patch``,
``daemon_deliver_remote``) that memory leaves as ``NotImplementedError`` are
fully implemented here. See ``src/mail/server/docs/reference/backends.md``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, NamedTuple

from mail_protocol.core.constants import LIST_ADDRESS_PREFIX
from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
from mail_protocol.core.lists import MAILList, MAILListInBackend
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
from mail_protocol.core.webhooks import MAILWebhook
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
    BoxFilterParams,
    DaemonDeliverLocalRequest,
    DaemonDeliverRemoteRequest,
    DraftPatchRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)

from mail_server.auth import get_password_hash, verify_password
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.sqlite.database import Database
from mail_server.backends.sqlite.repositories import (
    BOX_DRAFTS,
    BOX_INBOX,
    BOX_OUTBOX,
    BOX_TRASH,
    MailStore,
)

logger = logging.getLogger(__name__)


def _is_agent_recipient(address: str) -> bool:
    """
    Return True iff ``address`` is an *agent* address (``name@swarm@host``).

    Mirrors the memory backend: webhooks fire only for agent recipients, never
    for ``list:`` fan-out targets or 2-segment user/admin/daemon addresses.
    """

    if address.startswith(f"{LIST_ADDRESS_PREFIX}:"):
        return False
    return address.count("@") == 2


class _WebhookFire(NamedTuple):
    """A ``mail.delivered`` POST to schedule once the delivery txn commits."""

    url: str
    recipient: str
    message: MAILMessage
    secret: str
    list_address: str | None


class SQLiteBackend(MAILServerBackend):
    """A transactional ``MAILServerBackend`` over SQLite (SQLAlchemy async)."""

    def __init__(self, url: str) -> None:
        self._db = Database(url)
        # Set from the ``host`` kwarg on startup; admin CRUD builds full
        # addresses as ``f"{local}@{self.host}"``, matching the memory backend.
        self.host: str = ""
        # Retain references to in-flight webhook tasks so they are not GC'd
        # mid-flight; entries are discarded when each task completes.
        self._delivery_tasks: set[asyncio.Task[None]] = set()

    #
    # Lifecycle handlers
    #
    async def on_server_startup(self, **kwargs: Any) -> None:
        logger.info("initializing sqlite backend...")
        host = kwargs.get("host")
        if isinstance(host, str):
            self.host = host
        await self._db.create_schema()
        logger.info("sqlite backend initialization complete")

    async def on_server_shutdown(self, **kwargs: Any) -> None:
        logger.info("shutting down sqlite backend...")
        await self._db.dispose()
        logger.info("sqlite backend shutdown complete")

    #
    # User-agent handlers
    #
    async def get_user_agent(self, address: str) -> MAILUserAgentInBackend:
        async with self._db.session() as session:
            user_agent = await MailStore(session).user_agents.get(address)
        if user_agent is None:
            raise ValueError(f"user-agent with address {address} not found")
        return user_agent

    async def user_agent_exists(self, address: str) -> bool:
        async with self._db.session() as session:
            return await MailStore(session).user_agents.exists(address)

    async def reset_password(
        self, user_agent: MAILUserAgent, payload: AuthPasswordResetRequest
    ) -> str:
        ua_addr = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            ua_in_be = await store.user_agents.get(ua_addr)
            if ua_in_be is None:
                raise ValueError(f"user-agent with address {ua_addr} not found")
            if not verify_password(
                plain_password=payload.current_password,
                hashed_password=ua_in_be.hashed_password,
            ):
                raise ValueError("incorrect password")
            await store.user_agents.set_password(
                ua_addr, get_password_hash(payload.new_password)
            )
        return "success"

    #
    # Swarm endpoint handlers
    #
    async def get_swarms(self) -> list[MAILSwarmSummary]:
        async with self._db.session() as session:
            swarms = await MailStore(session).swarms.list_all()
        return [swarm.summarize() for swarm in swarms]

    async def get_swarm(self, swarm_name: str) -> MAILSwarm:
        async with self._db.session() as session:
            swarm = await MailStore(session).swarms.get(swarm_name)
        if swarm is None:
            raise ValueError(f"swarm with name {swarm_name} not found")
        return swarm

    async def get_swarm_health(self, swarm_name: str) -> str:
        async with self._db.session() as session:
            swarm = await MailStore(session).swarms.get(swarm_name)
        if swarm is None:
            raise ValueError(f"swarm with name {swarm_name} not found")
        return "ok"

    #
    # Inbox endpoint handlers
    #
    async def get_inbox(
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILInboxEntrySummary], int]:
        async with self._db.session() as session:
            return await MailStore(session).boxes.list_inbox(
                user_agent.get_address(), filters
            )

    async def get_inbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILInboxEntry:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_INBOX, message_id):
                raise ValueError(
                    f"message with ID {message_id} not found in inbox at "
                    f"address {ua_address}"
                )
            inbox_entry = await store.boxes.get_inbox_entry(message_id)
            if inbox_entry is None:
                raise ValueError(
                    f"message with ID {message_id} not found in inbox entries"
                )
            message = await store.messages.get(message_id)
            if message is None:
                raise ValueError(f"message with ID {message_id} not found in messages")
        return MAILInboxEntry(
            message=message,
            received_at=inbox_entry.received_at,
            delivered_by=inbox_entry.delivered_by,
        )

    async def delete_inbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILInboxEntry:
        """Move a message from the owner's inbox to their trash (one txn)."""

        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_INBOX, message_id):
                raise ValueError(
                    f"message with ID {message_id} not found in inbox at "
                    f"address {ua_address}"
                )
            inbox_entry = await store.boxes.get_inbox_entry(message_id)
            if inbox_entry is None:
                raise ValueError(
                    f"message with ID {message_id} not found in inbox entries"
                )
            message = await store.messages.get(message_id)
            if message is None:
                raise ValueError(f"message with ID {message_id} not found in messages")

            result = MAILInboxEntry(
                message=message,
                received_at=inbox_entry.received_at,
                delivered_by=inbox_entry.delivered_by,
            )

            trashed_at = datetime.now(UTC)
            await store.boxes.remove_membership(ua_address, BOX_INBOX, message_id)
            await store.boxes.add_membership(
                ua_address, BOX_TRASH, message_id, trashed_at
            )
            await store.boxes.upsert_trash_entry(
                MAILTrashEntry(message=message, trashed_at=trashed_at)
            )
            # Drop the shared inbox entry once no inbox references it anymore.
            if await store.boxes.count_item_members(BOX_INBOX, message_id) == 0:
                await store.boxes.delete_inbox_entry(message_id)

        return result

    #
    # Outbox endpoint handlers
    #
    async def get_outbox(
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILOutboxEntrySummary], int]:
        async with self._db.session() as session:
            return await MailStore(session).boxes.list_outbox(
                user_agent.get_address(), filters
            )

    async def get_outbox_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILOutboxEntry:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_OUTBOX, message_id):
                raise ValueError(
                    f"message with ID {message_id} not found in outbox at "
                    f"address {ua_address}"
                )
            outbox_entry = await store.boxes.get_outbox_entry(message_id)
            if outbox_entry is None:
                raise ValueError(
                    f"message with ID {message_id} not found in outbox entries"
                )
            message = await store.messages.get(message_id)
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
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILDraftsEntrySummary], int]:
        async with self._db.session() as session:
            return await MailStore(session).boxes.list_drafts(
                user_agent.get_address(), filters
            )

    async def post_draft(
        self, user_agent: MAILUserAgent, payload: DraftPostRequest
    ) -> MAILDraftsEntry:
        ua_address = user_agent.get_address()
        draft_id = str(uuid.uuid4())
        draft = MAILDraft(
            draft_id=draft_id,
            subject=payload.subject,
            body=payload.body,
            created_at=datetime.now(UTC),
            updated_at=None,
            reply_to=payload.reply_to,
            tags=payload.tags,
        )
        draft_entry = MAILDraftsEntry(draft=draft, sent_at=None)
        async with self._db.session() as session:
            store = MailStore(session)
            await store.boxes.upsert_draft_entry(draft_entry)
            await store.boxes.add_membership(
                ua_address, BOX_DRAFTS, draft_id, draft.created_at
            )
        return draft_entry

    async def get_draft(
        self, user_agent: MAILUserAgent, draft_id: str
    ) -> MAILDraftsEntry:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_DRAFTS, draft_id):
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box at "
                    f"address {ua_address}"
                )
            draft_entry = await store.boxes.get_draft_entry(draft_id)
        if draft_entry is None:
            raise ValueError(f"draft with ID {draft_id} not found in draft box entries")
        return draft_entry

    async def patch_draft(
        self,
        user_agent: MAILUserAgent,
        draft_id: str,
        payload: DraftPatchRequest,
    ) -> MAILDraftsEntry:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_DRAFTS, draft_id):
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box at "
                    f"address {ua_address}"
                )
            draft_entry = await store.boxes.get_draft_entry(draft_id)
            if draft_entry is None:
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box entries"
                )

            # Only fields explicitly supplied are modified. ``tags=[]`` is a
            # deliberate "clear all tags"; an unset field (None) is left alone.
            updated_fields: dict[str, Any] = {}
            if payload.subject is not None:
                updated_fields["subject"] = payload.subject
            if payload.body is not None:
                updated_fields["body"] = payload.body
            if payload.reply_to is not None:
                updated_fields["reply_to"] = payload.reply_to
            if payload.tags is not None:
                updated_fields["tags"] = payload.tags

            if not updated_fields:
                return draft_entry

            updated_draft = draft_entry.draft.model_copy(
                update={**updated_fields, "updated_at": datetime.now(UTC)}
            )
            updated_entry = draft_entry.model_copy(update={"draft": updated_draft})
            await store.boxes.upsert_draft_entry(updated_entry)
        return updated_entry

    async def delete_draft(
        self, user_agent: MAILUserAgent, draft_id: str
    ) -> MAILDraftsEntry:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_DRAFTS, draft_id):
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box at "
                    f"address {ua_address}"
                )
            draft_entry = await store.boxes.get_draft_entry(draft_id)
            if draft_entry is None:
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box entries"
                )
            await store.boxes.remove_membership(ua_address, BOX_DRAFTS, draft_id)
            await store.boxes.delete_draft_entry(draft_id)
        return draft_entry

    async def send_draft(
        self,
        user_agent: MAILUserAgent,
        draft_id: str,
        payload: DraftSendPostRequest,
    ) -> MAILMessage:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_DRAFTS, draft_id):
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box at "
                    f"address {ua_address}"
                )
            draft_entry = await store.boxes.get_draft_entry(draft_id)
            if draft_entry is None:
                raise ValueError(
                    f"draft with ID {draft_id} not found in draft box entries"
                )
            draft = draft_entry.draft

            message_id = str(uuid.uuid4())  # distinct from draft_id
            # Draft tags + send-time tags, order-preserving union.
            tags = list(draft.tags)
            for tag in payload.tags:
                if tag not in tags:
                    tags.append(tag)
            now = datetime.now(UTC)
            message = MAILMessage(
                mail_version="2.0",
                message_id=message_id,
                reply_to=draft.reply_to,
                sender=ua_address,
                recipients=payload.recipients,
                subject=draft.subject,
                body=draft.body,
                tags=tags,
                sent_at=now,
                metadata={},
            )
            outbox_entry = MAILOutboxEntrySummary(
                message_id=message_id,
                recipients=message.recipients,
                subject=message.subject,
                body_size=len(message.body),
                sent_at=now,
                delivered_at=None,
                delivered_by=None,
            )

            await store.messages.add(message)
            await store.boxes.upsert_outbox_entry(outbox_entry)
            await store.boxes.add_membership(ua_address, BOX_OUTBOX, message_id, now)
            await store.buffer.enqueue(message_id)
        return message

    #
    # Trash box endpoints
    #
    async def get_trash(
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILTrashEntrySummary], int]:
        async with self._db.session() as session:
            return await MailStore(session).boxes.list_trash(
                user_agent.get_address(), filters
            )

    async def get_trash_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILTrashEntry:
        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_TRASH, message_id):
                raise ValueError(
                    f"message with ID {message_id} not found in trash box at "
                    f"address {ua_address}"
                )
            trash_entry = await store.boxes.get_trash_entry(message_id)
        if trash_entry is None:
            raise ValueError(
                f"message with ID {message_id} not found in trash entries"
            )
        return trash_entry

    async def delete_trash_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILTrashEntry:
        """Hard-delete a trashed message from the owner's trash box."""

        ua_address = user_agent.get_address()
        async with self._db.session() as session:
            store = MailStore(session)
            if not await store.boxes.is_member(ua_address, BOX_TRASH, message_id):
                raise ValueError(
                    f"message with ID {message_id} not found in trash box at "
                    f"address {ua_address}"
                )
            trash_entry = await store.boxes.get_trash_entry(message_id)
            if trash_entry is None:
                raise ValueError(
                    f"message with ID {message_id} not found in trash entries"
                )
            await store.boxes.remove_membership(ua_address, BOX_TRASH, message_id)
            # Drop the shared trash entry once no trash references it; the
            # canonical ``messages`` row is retained (mirrors memory, which
            # never deletes messages).
            if await store.boxes.count_item_members(BOX_TRASH, message_id) == 0:
                await store.boxes.delete_trash_entry(message_id)
        return trash_entry

    async def clear_trash(
        self, user_agent: MAILUserAgent
    ) -> list[MAILTrashEntrySummary]:
        ua_address = user_agent.get_address()
        summaries: list[MAILTrashEntrySummary] = []
        async with self._db.session() as session:
            store = MailStore(session)
            for message_id in await store.boxes.list_item_ids(ua_address, BOX_TRASH):
                trash_entry = await store.boxes.get_trash_entry(message_id)
                if trash_entry is not None:
                    summaries.append(trash_entry.summarize())
                await store.boxes.remove_membership(ua_address, BOX_TRASH, message_id)
                if await store.boxes.count_item_members(BOX_TRASH, message_id) == 0:
                    await store.boxes.delete_trash_entry(message_id)
        return summaries

    #
    # Daemon-only endpoints
    #
    async def daemon_clear_message_buffer(self, daemon: MAILDaemon) -> list[str]:
        async with self._db.session() as session:
            return await MailStore(session).buffer.drain()

    async def daemon_deliver_local(
        self, daemon: MAILDaemon, payload: DaemonDeliverLocalRequest
    ) -> list[MAILMessageSummary]:
        delivered: list[MAILMessageSummary] = []
        fires: list[_WebhookFire] = []
        async with self._db.session() as session:
            store = MailStore(session)
            webhooks = await self._delivered_webhooks(store)
            for message_id in payload.message_ids:
                message = await store.messages.get(message_id)
                if message is None:
                    logger.warning(f"failed to get message by ID {message_id}")
                    continue

                delivered_time = datetime.now(UTC)
                # Mark the shared outbox entry delivered (it must already exist).
                outbox_entry = await store.boxes.get_outbox_entry(message_id)
                if outbox_entry is not None:
                    outbox_entry.delivered_at = delivered_time
                    outbox_entry.delivered_by = daemon.get_address()
                    await store.boxes.upsert_outbox_entry(outbox_entry)

                await self._deliver_one(
                    store,
                    daemon=daemon,
                    message=message,
                    delivered_time=delivered_time,
                    webhooks=webhooks,
                    fires=fires,
                )
                delivered.append(message.summarize())
        self._schedule_webhooks(fires)
        return delivered

    async def daemon_deliver_remote(
        self, daemon: MAILDaemon, payload: DaemonDeliverRemoteRequest
    ) -> list[MAILMessageSummary]:
        """
        Deliver messages authored by *remote* agents to local recipients.

        Mirrors ``daemon_deliver_local`` but the messages arrive in full from
        off-server, so they are persisted into the canonical ``messages`` store
        first; there is no local outbox to update (the sender is remote).

        TODO: the ``/daemon/deliver/remote`` HTTP route is still a
        router-level ``NotImplementedError`` stub, so this method is currently
        reachable only via direct backend calls/tests, not over the wire.
        """

        delivered: list[MAILMessageSummary] = []
        fires: list[_WebhookFire] = []
        async with self._db.session() as session:
            store = MailStore(session)
            webhooks = await self._delivered_webhooks(store)
            for message in payload.messages:
                if await store.messages.get(message.message_id) is None:
                    await store.messages.add(message)
                await self._deliver_one(
                    store,
                    daemon=daemon,
                    message=message,
                    delivered_time=datetime.now(UTC),
                    webhooks=webhooks,
                    fires=fires,
                )
                delivered.append(message.summarize())
        self._schedule_webhooks(fires)
        return delivered

    #
    # Delivery helpers (session-scoped; webhooks collected, fired post-commit)
    #
    async def _delivered_webhooks(self, store: MailStore) -> list[MAILWebhook]:
        return [
            wh
            for wh in await store.webhooks.list_all()
            if "mail.delivered" in wh.events
        ]

    async def _deliver_one(
        self,
        store: MailStore,
        *,
        daemon: MAILDaemon,
        message: MAILMessage,
        delivered_time: datetime,
        webhooks: list[MAILWebhook],
        fires: list[_WebhookFire],
    ) -> None:
        """Upsert the shared inbox entry and deliver to each recipient."""

        inbox_entry = MAILInboxEntrySummary(
            message_id=message.message_id,
            sender=message.sender,
            subject=message.subject,
            body_size=len(message.body),
            received_at=delivered_time,
            delivered_by=daemon.get_address(),
        )
        await store.boxes.upsert_inbox_entry(inbox_entry)

        for recipient in message.recipients:
            if recipient.startswith(f"{LIST_ADDRESS_PREFIX}:"):
                await self._fan_out_to_list(
                    store,
                    list_address=recipient,
                    message=message,
                    delivered_time=delivered_time,
                    webhooks=webhooks,
                    fires=fires,
                )
                continue
            await self._deliver_to_address(
                store,
                address=recipient,
                message=message,
                delivered_time=delivered_time,
                list_address=None,
                webhooks=webhooks,
                fires=fires,
            )

    async def _deliver_to_address(
        self,
        store: MailStore,
        *,
        address: str,
        message: MAILMessage,
        delivered_time: datetime,
        list_address: str | None,
        webhooks: list[MAILWebhook],
        fires: list[_WebhookFire],
    ) -> None:
        user_agent = await store.user_agents.get(address)
        if user_agent is None:
            logger.warning(f"failed to validate recipient address {address}")
            return
        ua_address = user_agent.get_address()
        # Idempotent: re-delivering the same message is a no-op.
        if not await store.boxes.is_member(ua_address, BOX_INBOX, message.message_id):
            await store.boxes.add_membership(
                ua_address, BOX_INBOX, message.message_id, delivered_time
            )

        # ``mail.delivered`` is agent-scoped: only ``name@swarm@host`` recipients
        # carry the swarm the webhook payload requires.
        if user_agent.user_agent.ua_type != "agent" or not _is_agent_recipient(
            address
        ):
            logger.debug(
                f"skipping `mail.delivered` webhooks for non-agent recipient {address}"
            )
            return
        for webhook in webhooks:
            fires.append(
                _WebhookFire(
                    url=webhook.url,
                    recipient=address,
                    message=message,
                    secret=webhook.secret,
                    list_address=list_address,
                )
            )

    async def _fan_out_to_list(
        self,
        store: MailStore,
        *,
        list_address: str,
        message: MAILMessage,
        delivered_time: datetime,
        webhooks: list[MAILWebhook],
        fires: list[_WebhookFire],
    ) -> None:
        mail_list = await store.lists.get_by_address(list_address)
        if mail_list is None:
            logger.warning(
                f"unknown list address in recipients; skipping: {list_address}"
            )
            return
        for member in mail_list.members:
            if member.startswith(f"{LIST_ADDRESS_PREFIX}:"):
                logger.warning(
                    f"nested list members are not supported in v1; "
                    f"skipping {member!r} in {list_address!r}"
                )
                continue
            await self._deliver_to_address(
                store,
                address=member,
                message=message,
                delivered_time=delivered_time,
                list_address=list_address,
                webhooks=webhooks,
                fires=fires,
            )

    def _schedule_webhooks(self, fires: list[_WebhookFire]) -> None:
        """Fire collected ``mail.delivered`` POSTs after the txn has committed."""

        for fire in fires:
            task = asyncio.create_task(
                self.handle_webhook_delivered_for_url(
                    url=fire.url,
                    recipient=fire.recipient,
                    message=fire.message,
                    secret=fire.secret,
                    list_address=fire.list_address,
                )
            )
            self._delivery_tasks.add(task)
            task.add_done_callback(self._delivery_tasks.discard)

    #
    # Administrator endpoints — agents
    #
    async def admin_get_agents(self, admin: MAILAdmin) -> list[str]:
        async with self._db.session() as session:
            agents = await MailStore(session).user_agents.list_by_type("agent")
        local_addrs: list[str] = []
        for agent in agents:
            name, swarm, _host = agent.get_address().split("@")
            local_addrs.append(f"{name}@{swarm}")
        return local_addrs

    async def admin_get_agent(
        self, admin: MAILAdmin, local_address: str
    ) -> MAILAgent:
        full_address = f"{local_address}@{self.host}"
        async with self._db.session() as session:
            agent = await MailStore(session).user_agents.get(full_address)
        if agent is None:
            raise ValueError(f"no agent found with address {local_address}")
        inner = agent.user_agent
        if not isinstance(inner, MAILAgent):
            raise ValueError(f"invalid agent address: {local_address}")
        return inner

    async def admin_post_agent(
        self, admin: MAILAdmin, payload: AdminAgentPostRequest
    ) -> MAILAgent:
        full_address = f"{payload.agent_name}@{payload.swarm_name}@{self.host}"
        agent = MAILAgent(
            ua_type="agent",
            name=payload.agent_name,
            swarm=payload.swarm_name,
            host=self.host,
        )
        async with self._db.session() as session:
            store = MailStore(session)
            if await store.user_agents.exists(full_address):
                raise ValueError(f"agent address already taken: {full_address}")
            await store.user_agents.add(
                MAILUserAgentInBackend(
                    user_agent=agent,
                    hashed_password=get_password_hash(payload.agent_password),
                )
            )
        return agent

    async def admin_delete_agent(
        self, admin: MAILAdmin, local_address: str
    ) -> MAILAgent:
        full_address = f"{local_address}@{self.host}"
        async with self._db.session() as session:
            store = MailStore(session)
            agent = await store.user_agents.get(full_address)
            if agent is None:
                raise ValueError(f"agent not found: {local_address}")
            inner = agent.user_agent
            if not isinstance(inner, MAILAgent):
                raise ValueError(f"invalid agent address: {local_address}")
            await store.user_agents.delete(full_address)
        return inner

    #
    # Administrator endpoints — daemons
    #
    async def admin_get_daemons(self, admin: MAILAdmin) -> list[str]:
        async with self._db.session() as session:
            daemons = await MailStore(session).user_agents.list_by_type("daemon")
        worker_names: list[str] = []
        for daemon in daemons:
            name, _host = daemon.get_address().split("@")
            worker_names.append(name.removeprefix("daemon:"))
        return worker_names

    async def admin_get_daemon(
        self, admin: MAILAdmin, worker_name: str
    ) -> MAILDaemon:
        full_address = f"daemon:{worker_name}@{self.host}"
        async with self._db.session() as session:
            daemon = await MailStore(session).user_agents.get(full_address)
        if daemon is None:
            raise ValueError(f"no daemon found with worker name {worker_name}")
        inner = daemon.user_agent
        if not isinstance(inner, MAILDaemon):
            raise ValueError(f"invalid worker name: {worker_name}")
        return inner

    async def admin_post_daemon(
        self, admin: MAILAdmin, payload: AdminDaemonPostRequest
    ) -> MAILDaemon:
        full_address = f"daemon:{payload.worker_name}@{self.host}"
        daemon = MAILDaemon(
            ua_type="daemon",
            worker_name=payload.worker_name,
            host=self.host,
        )
        async with self._db.session() as session:
            store = MailStore(session)
            if await store.user_agents.exists(full_address):
                raise ValueError(f"daemon address already taken: {full_address}")
            await store.user_agents.add(
                MAILUserAgentInBackend(
                    user_agent=daemon,
                    hashed_password=get_password_hash(payload.daemon_password),
                )
            )
        return daemon

    async def admin_delete_daemon(
        self, admin: MAILAdmin, worker_name: str
    ) -> MAILDaemon:
        full_address = f"daemon:{worker_name}@{self.host}"
        async with self._db.session() as session:
            store = MailStore(session)
            daemon = await store.user_agents.get(full_address)
            if daemon is None:
                raise ValueError(f"daemon not found: {worker_name}")
            inner = daemon.user_agent
            if not isinstance(inner, MAILDaemon):
                raise ValueError(f"invalid daemon worker name: {worker_name}")
            await store.user_agents.delete(full_address)
        return inner

    #
    # Administrator endpoints — users
    #
    async def admin_get_users(self, admin: MAILAdmin) -> list[str]:
        async with self._db.session() as session:
            users = await MailStore(session).user_agents.list_by_type("user")
        user_ids: list[str] = []
        for user in users:
            name, _host = user.get_address().split("@")
            user_ids.append(name.removeprefix("user:"))
        return user_ids

    async def admin_get_user(self, admin: MAILAdmin, user_id: str) -> MAILUser:
        full_address = f"user:{user_id}@{self.host}"
        async with self._db.session() as session:
            user = await MailStore(session).user_agents.get(full_address)
        if user is None:
            raise ValueError(f"no user found with ID {user_id}")
        inner = user.user_agent
        if not isinstance(inner, MAILUser):
            raise ValueError(f"invalid user ID: {user_id}")
        return inner

    async def admin_post_user(
        self, admin: MAILAdmin, payload: AdminUserPostRequest
    ) -> MAILUser:
        full_address = f"user:{payload.user_id}@{self.host}"
        user = MAILUser(ua_type="user", user_id=payload.user_id, host=self.host)
        async with self._db.session() as session:
            store = MailStore(session)
            if await store.user_agents.exists(full_address):
                raise ValueError(f"user address already taken: {full_address}")
            await store.user_agents.add(
                MAILUserAgentInBackend(
                    user_agent=user,
                    hashed_password=get_password_hash(payload.user_password),
                )
            )
        return user

    async def admin_delete_user(self, admin: MAILAdmin, user_id: str) -> MAILUser:
        full_address = f"user:{user_id}@{self.host}"
        async with self._db.session() as session:
            store = MailStore(session)
            user = await store.user_agents.get(full_address)
            if user is None:
                raise ValueError(f"user not found: {user_id}")
            inner = user.user_agent
            if not isinstance(inner, MAILUser):
                raise ValueError(f"invalid user ID: {user_id}")
            await store.user_agents.delete(full_address)
        return inner

    #
    # Administrator endpoints — swarms
    #
    async def admin_post_swarm(
        self, admin: MAILAdmin, payload: AdminSwarmPostRequest
    ) -> MAILSwarm:
        new_swarm = MAILSwarm(
            name=payload.name,
            description=payload.description,
            keywords=payload.keywords,
            agents=[],
            metadata={},
        )
        async with self._db.session() as session:
            store = MailStore(session)
            if await store.swarms.get(payload.name) is not None:
                raise ValueError(f"swarm with name {payload.name} already exists")
            await store.swarms.add(new_swarm)
        return new_swarm

    async def admin_delete_swarm(
        self, admin: MAILAdmin, swarm_name: str
    ) -> MAILSwarm:
        async with self._db.session() as session:
            store = MailStore(session)
            swarm = await store.swarms.delete(swarm_name)
        if swarm is None:
            raise ValueError(f"swarm with name {swarm_name} not found")
        return swarm

    #
    # Webhook handlers
    #
    async def admin_webhooks_get(self, admin: MAILAdmin) -> list[str]:
        async with self._db.session() as session:
            webhooks = await MailStore(session).webhooks.list_all()
        return [wh.webhook_id for wh in webhooks]

    async def admin_webhook_get(
        self, admin: MAILAdmin, webhook_id: str
    ) -> MAILWebhook:
        async with self._db.session() as session:
            webhook = await MailStore(session).webhooks.get_by_id(webhook_id)
        if webhook is None:
            raise ValueError(f"webhook with ID {webhook_id} not found")
        return webhook

    async def admin_webhook_post(
        self, admin: MAILAdmin, payload: AdminWebhooksPostRequest
    ) -> MAILWebhook:
        async with self._db.session() as session:
            store = MailStore(session)
            # Idempotent on URL: an existing webhook is returned unchanged.
            existing = await store.webhooks.get_by_url(payload.url)
            if existing is not None:
                return existing
            new_webhook = MAILWebhook(
                webhook_id=f"wh_{uuid.uuid4()}",
                url=payload.url,
                events=payload.events,
                secret=payload.secret,
            )
            await store.webhooks.add(new_webhook)
        return new_webhook

    async def admin_webhook_patch(
        self,
        admin: MAILAdmin,
        webhook_id: str,
        payload: AdminWebhooksPatchRequest,
    ) -> MAILWebhook:
        """Update an existing webhook's URL and/or secret, preserving its id."""

        async with self._db.session() as session:
            store = MailStore(session)
            existing = await store.webhooks.get_by_id(webhook_id)
            if existing is None:
                raise ValueError(f"webhook with ID {webhook_id} not found")
            updated = existing.model_copy(
                update={"url": payload.url, "secret": payload.secret}
            )
            # The table is keyed by URL; delete + re-add handles both an
            # in-place secret change and a URL (PK) move uniformly.
            await store.webhooks.delete_by_url(existing.url)
            await store.webhooks.add(updated)
        return updated

    async def admin_webhook_delete(
        self, admin: MAILAdmin, webhook_id: str
    ) -> MAILWebhook:
        async with self._db.session() as session:
            store = MailStore(session)
            webhook = await store.webhooks.get_by_id(webhook_id)
            if webhook is None:
                raise ValueError(f"webhook with ID {webhook_id} not found")
            await store.webhooks.delete_by_url(webhook.url)
        return webhook

    #
    # List endpoints
    #
    async def get_lists(self) -> list[MAILListInBackend]:
        async with self._db.session() as session:
            return await MailStore(session).lists.list_all()

    async def get_list(self, list_address: str) -> MAILListInBackend:
        async with self._db.session() as session:
            mail_list = await MailStore(session).lists.get_by_address(list_address)
        if mail_list is None:
            raise ValueError(f"list not found: {list_address}")
        return mail_list

    async def admin_get_lists(self, admin: MAILAdmin) -> list[MAILListInBackend]:
        return await self.get_lists()

    async def admin_get_list(
        self, admin: MAILAdmin, list_address: str
    ) -> MAILListInBackend:
        return await self.get_list(list_address)

    async def admin_post_list(
        self, admin: MAILAdmin, payload: AdminListPostRequest
    ) -> MAILListInBackend:
        mail_list = MAILList(
            name=payload.name,
            swarm=payload.swarm_name,
            host=self.host,
            owner=payload.owner,
            members=payload.members,
            policy=payload.policy,
        )
        address = mail_list.get_address()
        now = datetime.now(UTC)
        record = MAILListInBackend(
            **mail_list.model_dump(),
            list_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
        )
        async with self._db.session() as session:
            store = MailStore(session)
            if await store.lists.get_by_address(address) is not None:
                raise ValueError(f"list address already taken: {address}")
            await store.lists.add(record)
        return record

    async def admin_patch_list(
        self,
        admin: MAILAdmin,
        list_address: str,
        payload: AdminListPatchRequest,
    ) -> MAILListInBackend:
        async with self._db.session() as session:
            store = MailStore(session)
            existing = await store.lists.get_by_address(list_address)
            if existing is None:
                raise ValueError(f"list not found: {list_address}")
            if payload.policy is None:
                return existing
            updated = existing.model_copy(
                update={"policy": payload.policy, "updated_at": datetime.now(UTC)}
            )
            await store.lists.update(updated)
        return updated

    async def admin_delete_list(
        self, admin: MAILAdmin, list_address: str
    ) -> MAILListInBackend:
        async with self._db.session() as session:
            mail_list = await MailStore(session).lists.delete(list_address)
        if mail_list is None:
            raise ValueError(f"list not found: {list_address}")
        return mail_list

    async def add_list_member(
        self, list_address: str, member_address: str
    ) -> MAILListInBackend:
        async with self._db.session() as session:
            store = MailStore(session)
            existing = await store.lists.get_by_address(list_address)
            if existing is None:
                raise ValueError(f"list not found: {list_address}")
            if member_address in existing.members:
                return existing
            updated = existing.model_copy(
                update={
                    "members": [*existing.members, member_address],
                    "updated_at": datetime.now(UTC),
                }
            )
            await store.lists.update(updated)
        return updated

    async def remove_list_member(
        self, list_address: str, member_address: str
    ) -> MAILListInBackend:
        async with self._db.session() as session:
            store = MailStore(session)
            existing = await store.lists.get_by_address(list_address)
            if existing is None:
                raise ValueError(f"list not found: {list_address}")
            if member_address not in existing.members:
                return existing
            updated = existing.model_copy(
                update={
                    "members": [m for m in existing.members if m != member_address],
                    "updated_at": datetime.now(UTC),
                }
            )
            await store.lists.update(updated)
        return updated

    #
    # Message endpoints
    #
    async def get_message(self, message_id: str) -> MAILMessage:
        async with self._db.session() as session:
            message = await MailStore(session).messages.get(message_id)
        if message is None:
            raise ValueError(f"undefined message ID: {message_id}")
        return message
