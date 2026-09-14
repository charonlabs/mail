# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from mail_protocol.core.auth import RefreshTokenRecord
from mail_protocol.core.constants import LIST_ADDRESS_PREFIX
from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.federation import mail_address_host
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
from mail_server.backends.memory.fs import (
    load_bounce_emissions,
    load_delivery_targets,
    load_draft_entries,
    load_drafts,
    load_federation_inbound_receipts,
    load_federation_outbound,
    load_inbox_entries,
    load_inboxes,
    load_lists,
    load_message_buffer,
    load_messages,
    load_outbox_entries,
    load_outboxes,
    load_read_inbox,
    load_refresh_tokens,
    load_swarms,
    load_trash_entries,
    load_trashes,
    load_user_agents,
    load_webhooks,
    save_bounce_emissions,
    save_delivery_targets,
    save_draft_entries,
    save_drafts,
    save_federation_inbound_receipts,
    save_federation_outbound,
    save_inbox_entries,
    save_inboxes,
    save_lists,
    save_message_buffer,
    save_messages,
    save_outbox_entries,
    save_outboxes,
    save_read_inbox,
    save_refresh_tokens,
    save_swarms,
    save_trash_entries,
    save_trashes,
    save_user_agents,
    save_webhooks,
)
from mail_server.federation.addressing import build_message_delivery_plan
from mail_server.federation.records import (
    BounceEmission,
    InboundFederationReceipt,
    MessageDeliveryTarget,
    OutboundFederationDelivery,
)

logger = logging.getLogger(__name__)

_LOCAL_DELIVERY_LEASE = timedelta(minutes=5)


def _is_agent_recipient(address: str) -> bool:
    """
    Return True iff ``address`` is an *agent* address.

    Agent addresses are ``name@swarm@host`` (three @-segments). User,
    admin, and daemon addresses are ``prefix:name@host`` (two
    @-segments). List addresses (``list:name@swarm@host``) also have
    three segments but are routed via fan-out, not direct delivery —
    they shouldn't reach the webhook firing path, but the explicit
    ``list:`` exclusion is defensive.
    """
    if address.startswith(f"{LIST_ADDRESS_PREFIX}:"):
        return False
    return address.count("@") == 2


def _paginate_box(
    entries: list[Any], filters: BoxFilterParams, key: Callable[[Any], Any]
) -> tuple[list[Any], int]:
    """
    Sort ``entries`` by ``key`` (honoring ``filters.order``) and return one
    page per ``filters.limit`` / ``filters.offset``.

    Returns ``(page, total)`` where ``total`` is the count before slicing.
    """

    total = len(entries)
    ordered = sorted(entries, key=key, reverse=filters.order == "desc")
    page = ordered[filters.offset : filters.offset + filters.limit]
    return page, total


class MemoryBackend(MAILServerBackend):
    """
    A generic base class for the MAIL server backend.
    """

    def __init__(self, persistence_interval_seconds: float = 0) -> None:
        """
        Initialize the in-memory backend and persistence lifecycle state.
        """

        if persistence_interval_seconds < 0:
            raise ValueError("persistence interval must be non-negative")

        self.persistence_interval_seconds = persistence_interval_seconds
        self._persistence_lock = asyncio.Lock()
        self._checkpoint_task: asyncio.Task[None] | None = None

    def _snapshot_persistence_state(self) -> dict[str, Any]:
        """
        Build a stable snapshot of all collections persisted to disk.
        """

        return {
            "user_agents": dict(self.user_agents),
            "swarms": dict(self.swarms),
            "messages": dict(self.messages),
            "inbox_entries": dict(self.inbox_entries),
            "inboxes": {address: list(ids) for address, ids in self.inboxes.items()},
            "read_inbox": {
                address: set(ids) for address, ids in self.read_inbox.items()
            },
            "outbox_entries": dict(self.outbox_entries),
            "outboxes": {address: list(ids) for address, ids in self.outboxes.items()},
            "draft_entries": dict(self.draft_entries),
            "drafts": {address: list(ids) for address, ids in self.drafts.items()},
            "trash_entries": dict(self.trash_entries),
            "trashes": {address: list(ids) for address, ids in self.trashes.items()},
            "message_buffer": list(self.message_buffer),
            "webhooks": dict(self.webhooks),
            "lists": dict(self.lists),
            "refresh_tokens": dict(self.refresh_tokens),
            "delivery_targets": dict(self.delivery_targets),
            "federation_outbound": dict(self.federation_outbound),
            "federation_inbound_receipts": dict(self.federation_inbound_receipts),
            "bounce_emissions": dict(self.bounce_emissions),
        }

    async def persist(self, *, reason: str = "manual") -> None:
        """
        Persist the current in-memory state to the local filesystem.
        """

        async with self._persistence_lock:
            started_at = time.monotonic()
            snapshot = self._snapshot_persistence_state()
            logger.info("persisting memory backend state: reason=%s", reason)

            await save_user_agents(snapshot["user_agents"])
            await save_swarms(snapshot["swarms"])
            await save_messages(snapshot["messages"])
            await save_inbox_entries(snapshot["inbox_entries"])
            await save_inboxes(snapshot["inboxes"])
            await save_read_inbox(snapshot["read_inbox"])
            await save_outbox_entries(snapshot["outbox_entries"])
            await save_outboxes(snapshot["outboxes"])
            await save_draft_entries(snapshot["draft_entries"])
            await save_drafts(snapshot["drafts"])
            await save_trash_entries(snapshot["trash_entries"])
            await save_trashes(snapshot["trashes"])
            await save_message_buffer(snapshot["message_buffer"])
            await save_webhooks(snapshot["webhooks"])
            await save_lists(snapshot["lists"])
            await save_refresh_tokens(snapshot["refresh_tokens"])
            await save_delivery_targets(snapshot["delivery_targets"])
            await save_federation_outbound(snapshot["federation_outbound"])
            await save_federation_inbound_receipts(
                snapshot["federation_inbound_receipts"]
            )
            await save_bounce_emissions(snapshot["bounce_emissions"])

            elapsed = time.monotonic() - started_at
            logger.info(
                "memory backend state persisted: reason=%s elapsed=%.3fs",
                reason,
                elapsed,
            )

    async def _checkpoint_loop(self) -> None:
        """
        Periodically persist the memory backend until shutdown.
        """

        logger.info(
            "memory backend periodic checkpoint task started: interval=%ss",
            self.persistence_interval_seconds,
        )
        try:
            while True:
                await asyncio.sleep(self.persistence_interval_seconds)
                try:
                    await self.persist(reason="periodic")
                except Exception:
                    logger.exception("memory backend periodic checkpoint failed")
        finally:
            logger.info("memory backend periodic checkpoint task stopped")

    def _start_periodic_checkpoint(self) -> None:
        """
        Start periodic persistence if configured.
        """

        if self.persistence_interval_seconds <= 0:
            return
        if self._checkpoint_task is not None and not self._checkpoint_task.done():
            return

        self._checkpoint_task = asyncio.create_task(
            self._checkpoint_loop(),
            name="mail-memory-backend-checkpoint",
        )

    async def _stop_periodic_checkpoint(self) -> None:
        """
        Stop periodic persistence before final shutdown persistence.
        """

        task = self._checkpoint_task
        self._checkpoint_task = None
        if task is None:
            return

        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("memory backend periodic checkpoint task failed")

    #
    # Lifecyle handlers
    #
    async def on_server_startup(self, **kwargs: Any) -> None:
        """
        Handle backend events on server startup.
        """

        logger.info("initializing backend...")

        self.user_agents: dict[str, MAILUserAgentInBackend] = await load_user_agents()
        """
        A dict of all user-agents known to this MAIL server.
        Keys: user-agent addresses
        Values: MAILUserAgentInBackend instances
        """

        self.swarms: dict[str, MAILSwarm] = await load_swarms()
        """
        A dict of all exposed MAIL swarms.
        Keys: swarm names
        Values: MAILSwarm instances
        """

        self.messages: dict[str, MAILMessage] = await load_messages()
        """
        A dict of all MAIL messages known to this server.
        Keys: message IDs
        Values: MAILMessage instances
        """

        self.inbox_entries: dict[
            str, MAILInboxEntrySummary
        ] = await load_inbox_entries()
        """
        A dict of all MAIL inbox entries on this server.
        Keys: message IDs
        Values: MAILInboxEntrySummary instances
        """

        self.inboxes: dict[str, list[str]] = await load_inboxes()
        """
        A dict of all local MAIL inboxes by user-agent.
        Keys: user-agent addresses
        Values: list of inbox entry message IDs
        """

        self.read_inbox: dict[str, set[str]] = await load_read_inbox()
        """
        Per-owner inbox read state (the in-memory analogue of
        ``mailbox_items.is_read``). A message is unread unless its id is present
        in the owner's set.
        Keys: user-agent addresses
        Values: set of read inbox message IDs
        """

        self.outbox_entries: dict[
            str, MAILOutboxEntrySummary
        ] = await load_outbox_entries()
        """
        A dict of all MAIL outbox entries on this server.
        Keys: message IDs
        Values: MAILOutboxEntrySummary instances
        """

        self.outboxes: dict[str, list[str]] = await load_outboxes()
        """
        A dict of all local MAIL outboxes by user-agent.
        Keys: user-agent addresses
        Values: list of outbox entry message IDs
        """

        self.draft_entries: dict[str, MAILDraftsEntry] = await load_draft_entries()
        """
        A dict of all MAIL draft entries on this server.
        Keys: draft IDs
        Values: MAILDraftsEntry instances
        """

        self.drafts: dict[str, list[str]] = await load_drafts()
        """
        A dict of all local MAIL draft boxes by user-agent.
        Keys: user-agent addresses
        Values: list of draft entry draft IDs
        """

        self.trash_entries: dict[str, MAILTrashEntry] = await load_trash_entries()
        """
        A dict of all MAIL trash entries on this server.
        Keys: message IDs
        Values: MAILTrashEntry instances
        """

        self.trashes: dict[str, list[str]] = await load_trashes()
        """
        A dict of all local MAIL trash boxes by user-agent.
        Keys: user-agent addresses
        Values: list of trash entry message IDs
        """

        self.message_buffer: list[str] = await load_message_buffer()
        """
        A list of all MAIL messages in the delivery buffer.
        Items: message IDs
        """

        self.webhooks: dict[str, MAILWebhook] = await load_webhooks()
        """
        A dict of all server webhooks.
        Keys: webhook URLs
        Values: MAILWebhook instances
        """

        self.lists: dict[str, MAILListInBackend] = await load_lists()
        """
        A dict of all MAIL lists known to this server.
        Keys: list addresses (``list:<name>@<swarm>@<host>``)
        Values: MAILListInBackend instances
        """

        self.refresh_tokens: dict[str, RefreshTokenRecord] = await load_refresh_tokens()
        """
        A dict of all stored refresh tokens on this server.
        Keys: token hashes (sha256 hex)
        Values: RefreshTokenRecord instances
        """

        self.delivery_targets: dict[
            str, MessageDeliveryTarget
        ] = await load_delivery_targets()
        self.federation_outbound: dict[
            str, OutboundFederationDelivery
        ] = await load_federation_outbound()
        self.federation_inbound_receipts: dict[
            str, InboundFederationReceipt
        ] = await load_federation_inbound_receipts()
        self.bounce_emissions: dict[str, BounceEmission] = await load_bounce_emissions()

        host = kwargs.get("host")
        if host is not None:
            if isinstance(host, str):
                self.host = host

        self._start_periodic_checkpoint()

        logger.info("backend initialization complete")

    async def on_server_shutdown(self, **kwargs: Any) -> None:
        """
        Handle backend events on server shutdown.
        """

        logger.info("shutting down backend...")

        await self._stop_periodic_checkpoint()
        await self.persist(reason="shutdown")

        logger.info("backend shutdown complete")

    #
    # User-agent handlers
    #
    async def get_user_agent(self, address: str) -> MAILUserAgentInBackend:
        """
        Get the existing user-agent by MAIL address in the server backend.
        """

        user_agent = self.user_agents.get(address)
        if user_agent is None:
            raise ValueError(f"user-agent with address {address} not found")
        return user_agent

    async def user_agent_exists(self, address: str) -> bool:
        """
        Return True if the user-agent exists in the backend, otherwise False.
        """

        return address in self.user_agents

    async def reset_password(
        self, user_agent: MAILUserAgent, payload: AuthPasswordResetRequest
    ) -> str:
        """
        Reset the password for an authenticated user-agent.
        """

        ua_addr = user_agent.get_address()
        ua_in_be = self.user_agents.get(ua_addr)
        if ua_in_be is None:
            raise ValueError(f"user-agent with address {ua_addr} not found")
        pwd_hash = ua_in_be.hashed_password
        pwd_current = payload.current_password
        if not verify_password(plain_password=pwd_current, hashed_password=pwd_hash):
            raise ValueError("incorrect password")
        pwd_hash_new = get_password_hash(payload.new_password)
        ua_in_be.hashed_password = pwd_hash_new

        self.user_agents.update({ua_addr: ua_in_be})

        return "success"

    #
    # Refresh token handlers
    #
    async def create_refresh_token(
        self,
        owner_address: str,
        token_hash: str,
        family_id: str,
        expires_at: datetime,
    ) -> None:
        """
        Persist a newly-issued refresh token.
        """

        self.refresh_tokens[token_hash] = RefreshTokenRecord(
            token_hash=token_hash,
            family_id=family_id,
            owner_address=owner_address,
            issued_at=datetime.now(UTC),
            expires_at=expires_at,
        )

    async def get_refresh_token(self, token_hash: str) -> RefreshTokenRecord | None:
        """
        Get a stored refresh token by its hash, or None if it does not exist.
        """

        return self.refresh_tokens.get(token_hash)

    async def rotate_refresh_token(self, old_hash: str, new_hash: str) -> None:
        """
        Rotate a refresh token: revoke the old one and mint a replacement in the
        same family carrying the old token's ``expires_at`` forward.
        """

        old = self.refresh_tokens.get(old_hash)
        if old is None:
            raise ValueError(f"refresh token {old_hash} not found")

        now = datetime.now(UTC)
        old.revoked = True
        old.rotated_at = now
        self.refresh_tokens[old_hash] = old

        self.refresh_tokens[new_hash] = RefreshTokenRecord(
            token_hash=new_hash,
            family_id=old.family_id,
            owner_address=old.owner_address,
            issued_at=now,
            expires_at=old.expires_at,
        )

    async def revoke_refresh_family(self, family_id: str) -> None:
        """
        Revoke every refresh token in a family.
        """

        for record in self.refresh_tokens.values():
            if record.family_id == family_id:
                record.revoked = True

    async def revoke_all_refresh_tokens(self, owner_address: str) -> None:
        """
        Revoke every refresh token owned by an address.
        """

        for record in self.refresh_tokens.values():
            if record.owner_address == owner_address:
                record.revoked = True

    async def purge_expired_refresh_tokens(self) -> int:
        """
        Delete every refresh token whose ``expires_at`` is in the past.
        """

        now = datetime.now(UTC)
        expired = [
            token_hash
            for token_hash, record in self.refresh_tokens.items()
            if record.expires_at < now
        ]
        for token_hash in expired:
            del self.refresh_tokens[token_hash]
        return len(expired)

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
    # Box query helpers
    #
    def _box_sort_key(
        self, filters: BoxFilterParams, entered_field: str
    ) -> Callable[[Any], Any]:
        """
        Build the sort key for a "GET box" page.

        ``entered_at`` sorts by ``entered_field`` — the timestamp at which the
        entry landed in this box. ``sent_at`` sorts by the underlying
        ``MAILMessage.sent_at`` (resolved via ``self.messages``), which is the
        original send time and is distinct from arrival for inbox/trash. Only
        valid for boxes whose entries reference a real message — drafts reject
        ``sent_at`` at the router, since a draft has no send time.
        """

        if filters.sort_by == "sent_at":
            return lambda entry: self.messages[entry.message_id].sent_at
        return lambda entry: getattr(entry, entered_field)

    #
    # Inbox endpoint handlers
    #
    async def get_inbox(
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILInboxEntrySummary], int]:
        """
        Get a sorted, paginated page of the user-agent's inbox.
        """

        ua_address = user_agent.get_address()
        inbox_msg_ids = self.inboxes.get(ua_address)
        if inbox_msg_ids is None:
            raise ValueError(f"no inbox found for address {ua_address}")

        read = self.read_inbox.get(ua_address, set())
        inbox_entries: list[MAILInboxEntrySummary] = []
        for msg_id in inbox_msg_ids:
            inbox_entry = self.inbox_entries.get(msg_id)
            if inbox_entry is None:
                raise ValueError(f"no inbox entry found for message ID {msg_id}")
            # ``inbox_entries`` is shared across recipients; copy so this owner's
            # read state never leaks onto the shared entry.
            inbox_entries.append(
                inbox_entry.model_copy(update={"is_read": msg_id in read})
            )

        return _paginate_box(
            inbox_entries, filters, self._box_sort_key(filters, "received_at")
        )

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

        # Opening a message marks it read for this owner.
        self.read_inbox.setdefault(ua_address, set()).add(message_id)

        return MAILInboxEntry(
            message=message,
            received_at=inbox_entry.received_at,
            delivered_by=inbox_entry.delivered_by,
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
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILOutboxEntrySummary], int]:
        """
        Get a sorted, paginated page of the user-agent's outbox.
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

        return _paginate_box(
            outbox_entries, filters, self._box_sort_key(filters, "sent_at")
        )

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
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILDraftsEntrySummary], int]:
        """
        Get a sorted, paginated page of the user-agent's draft box.
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

        # Drafts have no send time, so `sort_by=sent_at` is rejected at the
        # router; only `entered_at` (created_at) reaches here.
        return _paginate_box(draft_entries, filters, lambda entry: entry.created_at)

    async def post_draft(
        self,
        user_agent: MAILUserAgent,
        payload: DraftPostRequest,
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
            reply_to=payload.reply_to,
            tags=payload.tags,
        )
        draft_entry = MAILDraftsEntry(draft=draft, sent_at=None)

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

    async def patch_draft(
        self,
        user_agent: MAILUserAgent,
        draft_id: str,
        payload: DraftPatchRequest,
    ) -> MAILDraftsEntry:
        """
        Update mutable fields on an existing message draft for this user-agent.

        Only the fields supplied on ``payload`` are modified; ``updated_at`` is
        refreshed whenever a successful edit is applied.
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

        # Only the fields explicitly supplied on the request are modified. A
        # field left unset (``None``) is not part of the update — except
        # ``tags``, where an empty list is a deliberate "clear all tags".
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
        self.draft_entries[draft_id] = updated_entry

        return updated_entry

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
        payload: DraftSendPostRequest,
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

        message_id = str(uuid.uuid4())  # make this different from draft_id
        # Tags on the draft and tags supplied at send time are merged as an
        # order-preserving union: draft tags first, then any new send tags.
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
        delivery_plan = build_message_delivery_plan(
            message,
            local_host=self.host,
            created_at=now,
        )

        # add to server messages
        self.messages.update({message_id: message})
        # add to server outbox_entries
        self.outbox_entries.update({message_id: outbox_entry})
        # add to user-agent's outbox
        self.outboxes[ua_address].append(message_id)
        self.delivery_targets.update(
            {target.target_id: target for target in delivery_plan.targets}
        )
        self.federation_outbound.update(
            {delivery.envelope_id: delivery for delivery in delivery_plan.outbound}
        )
        if delivery_plan.has_local_target:
            self.message_buffer.append(message_id)

        return message

    #
    # Trash box endpoints
    #
    async def get_trash(
        self, user_agent: MAILUserAgent, filters: BoxFilterParams
    ) -> tuple[list[MAILTrashEntrySummary], int]:
        """
        Get a sorted, paginated page of the user-agent's trash box.
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

        return _paginate_box(
            trash_entries, filters, self._box_sort_key(filters, "trashed_at")
        )

    async def get_trash_message(
        self, user_agent: MAILUserAgent, message_id: str
    ) -> MAILTrashEntry:
        """
        Get a specific trashed message by ID for this user-agent.
        """

        ua_address = user_agent.get_address()
        trash_msg_ids = self.trashes.get(ua_address)
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
    async def daemon_clear_message_buffer(
        self,
        daemon: MAILDaemon,
    ) -> list[str]:
        """
        Obtain all messages to be delivered on the server and clear the buffer.
        """

        message_buffer = deepcopy(self.message_buffer)
        self.message_buffer.clear()
        now = datetime.now(UTC)
        claimed: list[MessageDeliveryTarget] = []
        for target in sorted(
            self.delivery_targets.values(),
            key=lambda item: (item.created_at, item.target_id),
        ):
            from_buffer = (
                target.kind == "local"
                and target.status == "pending"
                and target.message_id in message_buffer
            )
            expired = (
                target.kind == "local"
                and target.status == "leased"
                and target.lease_until is not None
                and target.lease_until <= now
            )
            if not (from_buffer or expired):
                continue
            leased = MessageDeliveryTarget.model_validate(
                {
                    **target.model_dump(),
                    "status": "leased",
                    "lease_owner": daemon.get_address(),
                    "lease_until": now + _LOCAL_DELIVERY_LEASE,
                    "updated_at": now,
                }
            )
            self.delivery_targets[target.target_id] = leased
            claimed.append(leased)

        claimed_ids = [target.message_id for target in claimed]
        claimed_set = set(claimed_ids)
        known_targets = {
            target.message_id
            for target in self.delivery_targets.values()
            if target.kind == "local" and target.message_id in message_buffer
        }
        result = [
            item
            for item in message_buffer
            if item in claimed_set or item not in known_targets
        ]
        result.extend(item for item in claimed_ids if item not in message_buffer)
        return result

    async def daemon_deliver_local(
        self,
        daemon: MAILDaemon,
        payload: DaemonDeliverLocalRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by other local agents.
        """

        message_ids = payload.message_ids
        messages: list[MAILMessageSummary] = []
        for msg_id in message_ids:
            try:
                message = await self.get_message(msg_id)
            except Exception:
                logger.warning(f"failed to get message by ID {msg_id}")
                continue

            delivered_time = datetime.now(UTC)
            delivery_message = self._local_delivery_message(message)

            # 1. create shared inbox entry
            inbox_entry = MAILInboxEntrySummary(
                message_id=message.message_id,
                sender=message.sender,
                subject=message.subject,
                body_size=len(message.body),
                received_at=delivered_time,
                delivered_by=daemon.get_address(),
            )
            self.inbox_entries.update({inbox_entry.message_id: inbox_entry})

            # 2. update the inbox of each recipient. Recipients with the
            # ``list:`` prefix are fan-out targets; expand to members,
            # deliver to each, and tag the per-member webhook with the
            # originating list address. Direct recipients are delivered
            # as before with no list tag.
            for rec in delivery_message.recipients:
                if rec.startswith(f"{LIST_ADDRESS_PREFIX}:"):
                    await self._fan_out_to_list(
                        list_address=rec,
                        inbox_entry=inbox_entry,
                        message=delivery_message,
                    )
                    continue
                await self._deliver_to_address(
                    address=rec,
                    inbox_entry=inbox_entry,
                    message=delivery_message,
                    list_address=None,
                )

            self._complete_local_delivery_targets(
                message_id=message.message_id,
                completed_at=delivered_time,
                delivered_by=daemon.get_address(),
            )

            messages.append(message.summarize())

        return messages

    async def daemon_deliver_remote(
        self,
        daemon: MAILDaemon,
        payload: DaemonDeliverRemoteRequest,
    ) -> list[MAILMessageSummary]:
        """
        Deliver MAIL message(s) to local agents sent by remote agents.
        """

        raise NotImplementedError

    def _local_delivery_message(self, message: MAILMessage) -> MAILMessage:
        local_targets = [
            target
            for target in self.delivery_targets.values()
            if target.message_id == message.message_id and target.kind == "local"
        ]
        if not local_targets:
            return message
        recipients = [
            recipient for target in local_targets for recipient in target.recipients
        ]
        return message.model_copy(update={"recipients": recipients})

    def _complete_local_delivery_targets(
        self,
        *,
        message_id: str,
        completed_at: datetime,
        delivered_by: str,
    ) -> None:
        targets = [
            target
            for target in self.delivery_targets.values()
            if target.message_id == message_id
        ]
        local_targets = [target for target in targets if target.kind == "local"]
        if not local_targets:
            outbox_entry = self.outbox_entries.get(message_id)
            if outbox_entry is not None:
                outbox_entry.delivered_at = completed_at
                outbox_entry.delivered_by = delivered_by
            return
        for target in local_targets:
            if target.status == "succeeded":
                continue
            self.delivery_targets[target.target_id] = (
                MessageDeliveryTarget.model_validate(
                    {
                        **target.model_dump(),
                        "status": "succeeded",
                        "lease_owner": None,
                        "lease_until": None,
                        "failure_code": None,
                        "updated_at": completed_at,
                        "completed_at": completed_at,
                    }
                )
            )
        if all(
            target.status == "succeeded"
            for target in self.delivery_targets.values()
            if target.message_id == message_id
        ):
            outbox_entry = self.outbox_entries.get(message_id)
            if outbox_entry is not None and outbox_entry.delivered_at is None:
                outbox_entry.delivered_at = completed_at
                outbox_entry.delivered_by = delivered_by

    #
    # Durable federation state
    #
    async def get_message_delivery_targets(
        self, message_id: str
    ) -> list[MessageDeliveryTarget]:
        return sorted(
            (
                target
                for target in self.delivery_targets.values()
                if target.message_id == message_id
            ),
            key=lambda target: (target.created_at, target.target_id),
        )

    async def get_outbound_federation_deliveries(
        self, message_id: str
    ) -> list[OutboundFederationDelivery]:
        return sorted(
            (
                delivery
                for delivery in self.federation_outbound.values()
                if delivery.message_id == message_id
            ),
            key=lambda delivery: (delivery.created_at, delivery.envelope_id),
        )

    async def claim_due_federation_deliveries(
        self,
        *,
        now: datetime,
        lease_owner: str,
        lease_duration: timedelta,
        limit: int,
    ) -> list[OutboundFederationDelivery]:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if limit <= 0:
            raise ValueError("claim limit must be positive")
        due = sorted(
            (
                delivery
                for delivery in self.federation_outbound.values()
                if (delivery.status == "pending" and delivery.next_attempt_at <= now)
                or (
                    delivery.status == "leased"
                    and delivery.lease_until is not None
                    and delivery.lease_until <= now
                )
            ),
            key=lambda delivery: (delivery.next_attempt_at, delivery.envelope_id),
        )[:limit]
        claimed: list[OutboundFederationDelivery] = []
        for delivery in due:
            leased = OutboundFederationDelivery.model_validate(
                {
                    **delivery.model_dump(),
                    "status": "leased",
                    "lease_owner": lease_owner,
                    "lease_until": now + lease_duration,
                    "updated_at": now,
                }
            )
            self.federation_outbound[delivery.envelope_id] = leased
            target = self.delivery_targets[delivery.target_id]
            self.delivery_targets[target.target_id] = (
                MessageDeliveryTarget.model_validate(
                    {
                        **target.model_dump(),
                        "status": "leased",
                        "lease_owner": lease_owner,
                        "lease_until": now + lease_duration,
                        "updated_at": now,
                    }
                )
            )
            claimed.append(leased)
        return claimed

    @staticmethod
    def _require_outbound_lease(
        delivery: OutboundFederationDelivery,
        lease_owner: str,
        action_at: datetime,
    ) -> None:
        if (
            delivery.status != "leased"
            or delivery.lease_owner != lease_owner
            or delivery.lease_until is None
            or delivery.lease_until < action_at
        ):
            raise ValueError(
                "outbound federation delivery is not leased by this worker"
            )

    async def record_federation_attempt(
        self,
        envelope_id: str,
        *,
        lease_owner: str,
        attempted_at: datetime,
        next_attempt_at: datetime,
        http_status: int | None = None,
        error: str | None = None,
    ) -> OutboundFederationDelivery:
        delivery = self.federation_outbound.get(envelope_id)
        if delivery is None:
            raise ValueError(f"outbound envelope {envelope_id} not found")
        self._require_outbound_lease(delivery, lease_owner, attempted_at)
        updated = OutboundFederationDelivery.model_validate(
            {
                **delivery.model_dump(),
                "status": "pending",
                "attempt_count": delivery.attempt_count + 1,
                "attempt_timestamps": [*delivery.attempt_timestamps, attempted_at],
                "next_attempt_at": next_attempt_at,
                "lease_owner": None,
                "lease_until": None,
                "last_http_status": http_status,
                "last_error": error,
                "updated_at": attempted_at,
            }
        )
        target = self.delivery_targets[delivery.target_id]
        updated_target = MessageDeliveryTarget.model_validate(
            {
                **target.model_dump(),
                "status": "pending",
                "lease_owner": None,
                "lease_until": None,
                "updated_at": attempted_at,
            }
        )
        self.federation_outbound[envelope_id] = updated
        self.delivery_targets[target.target_id] = updated_target
        return updated

    async def complete_federation_delivery(
        self,
        envelope_id: str,
        *,
        lease_owner: str,
        completed_at: datetime,
        delivered_by: str | None = None,
    ) -> OutboundFederationDelivery:
        delivery = self.federation_outbound.get(envelope_id)
        if delivery is None:
            raise ValueError(f"outbound envelope {envelope_id} not found")
        if delivery.status == "succeeded":
            return delivery
        self._require_outbound_lease(delivery, lease_owner, completed_at)
        completed = OutboundFederationDelivery.model_validate(
            {
                **delivery.model_dump(),
                "status": "succeeded",
                "attempt_count": delivery.attempt_count + 1,
                "attempt_timestamps": [*delivery.attempt_timestamps, completed_at],
                "lease_owner": None,
                "lease_until": None,
                "updated_at": completed_at,
                "completed_at": completed_at,
            }
        )
        target = self.delivery_targets[delivery.target_id]
        completed_target = MessageDeliveryTarget.model_validate(
            {
                **target.model_dump(),
                "status": "succeeded",
                "lease_owner": None,
                "lease_until": None,
                "failure_code": None,
                "updated_at": completed_at,
                "completed_at": completed_at,
            }
        )
        self.federation_outbound[envelope_id] = completed
        self.delivery_targets[target.target_id] = completed_target
        targets = [
            item
            for item in self.delivery_targets.values()
            if item.message_id == delivery.message_id
        ]
        if targets and all(item.status == "succeeded" for item in targets):
            outbox_entry = self.outbox_entries.get(delivery.message_id)
            if outbox_entry is not None and outbox_entry.delivered_at is None:
                outbox_entry.delivered_at = completed_at
                outbox_entry.delivered_by = delivered_by
        return completed

    async def fail_federation_delivery(
        self,
        envelope_id: str,
        *,
        lease_owner: str,
        completed_at: datetime,
        failure_code: str,
        http_status: int | None = None,
        error: str | None = None,
    ) -> OutboundFederationDelivery:
        delivery = self.federation_outbound.get(envelope_id)
        if delivery is None:
            raise ValueError(f"outbound envelope {envelope_id} not found")
        if delivery.status == "dead_letter":
            return delivery
        self._require_outbound_lease(delivery, lease_owner, completed_at)
        failed = OutboundFederationDelivery.model_validate(
            {
                **delivery.model_dump(),
                "status": "dead_letter",
                "attempt_count": delivery.attempt_count + 1,
                "attempt_timestamps": [*delivery.attempt_timestamps, completed_at],
                "lease_owner": None,
                "lease_until": None,
                "last_http_status": http_status,
                "last_error": error,
                "updated_at": completed_at,
                "completed_at": completed_at,
            }
        )
        target = self.delivery_targets[delivery.target_id]
        failed_target = MessageDeliveryTarget.model_validate(
            {
                **target.model_dump(),
                "status": "failed",
                "lease_owner": None,
                "lease_until": None,
                "failure_code": failure_code,
                "updated_at": completed_at,
                "completed_at": completed_at,
            }
        )
        self.federation_outbound[envelope_id] = failed
        self.delivery_targets[target.target_id] = failed_target
        return failed

    async def accept_inbound_federation(
        self,
        receipt: InboundFederationReceipt,
        message: MAILMessage,
    ) -> bool:
        if receipt.inner_message_id != message.message_id:
            raise ValueError("receipt inner_message_id does not match message")
        await self.purge_expired_federation_receipts(now=receipt.accepted_at)
        if receipt.envelope_id in self.federation_inbound_receipts:
            return False
        existing = self.messages.get(message.message_id)
        if existing is not None and existing.model_dump(
            mode="json"
        ) != message.model_dump(mode="json"):
            raise ValueError("message ID collides with different content")

        targets = [
            target
            for target in self.delivery_targets.values()
            if target.message_id == message.message_id
            and target.origin == "inbound"
            and target.kind == "local"
        ]
        target: MessageDeliveryTarget | None = None
        if not targets:
            target = MessageDeliveryTarget(
                target_id=str(uuid.uuid4()),
                message_id=message.message_id,
                origin="inbound",
                kind="local",
                destination_host=mail_address_host(message.recipients[0]),
                recipients=message.recipients,
                created_at=receipt.accepted_at,
                updated_at=receipt.accepted_at,
            )

        self.federation_inbound_receipts[receipt.envelope_id] = receipt
        if existing is None:
            self.messages[message.message_id] = message
        if target is not None:
            self.delivery_targets[target.target_id] = target
            self.message_buffer.append(message.message_id)
        return True

    async def purge_expired_federation_receipts(self, *, now: datetime) -> int:
        expired = [
            envelope_id
            for envelope_id, receipt in self.federation_inbound_receipts.items()
            if receipt.expires_at <= now
        ]
        for envelope_id in expired:
            del self.federation_inbound_receipts[envelope_id]
        return len(expired)

    async def record_bounce_emission(self, emission: BounceEmission) -> None:
        if emission.emission_id in self.bounce_emissions:
            raise ValueError(f"bounce emission {emission.emission_id} already exists")
        self.bounce_emissions[emission.emission_id] = emission

    async def count_bounce_emissions_since(
        self, original_sender: str, *, since: datetime
    ) -> int:
        return sum(
            emission.original_sender == original_sender
            and emission.emitted_at >= since
            and emission.outcome == "emitted"
            for emission in self.bounce_emissions.values()
        )

    #
    # Administrator endpoints
    #
    async def admin_get_agents(
        self,
        admin: MAILAdmin,
    ) -> list[str]:
        """
        Get a list of agents by local address (agent@swarm) registered on this server.
        """

        agents = [
            addr
            for addr, ua in self.user_agents.items()
            if ua.user_agent.ua_type == "agent"
        ]
        local_addrs: list[str] = []
        for agent in agents:
            name, swarm, _host = agent.split("@")
            local_addrs.append(f"{name}@{swarm}")

        return local_addrs

    async def admin_get_agent(
        self,
        admin: MAILAdmin,
        local_address: str,
    ) -> MAILAgent:
        """
        Get a specific registered agent by local address (agent@swarm).
        """

        full_address = f"{local_address}@{self.host}"
        agent = self.user_agents.get(full_address)
        if agent is None:
            raise ValueError(f"no agent found with address {local_address}")
        if agent.user_agent.ua_type != "agent":
            raise ValueError(f"invalid agent address: {local_address}")

        return agent.user_agent

    async def admin_post_agent(
        self,
        admin: MAILAdmin,
        payload: AdminAgentPostRequest,
    ) -> MAILAgent:
        """
        Create a new MAIL agent with the specified credentials.
        """

        full_address = f"{payload.agent_name}@{payload.swarm_name}@{self.host}"
        if self.user_agents.get(full_address):
            raise ValueError(f"agent address already taken: {full_address}")

        agent = MAILAgent(
            ua_type="agent",
            name=payload.agent_name,
            swarm=payload.swarm_name,
            host=self.host,
        )

        # add new agent to self.user_agents
        ua_in_be = MAILUserAgentInBackend(
            user_agent=agent, hashed_password=get_password_hash(payload.agent_password)
        )
        self.user_agents.update({full_address: ua_in_be})

        # add new inbox to self.inboxes
        self.inboxes.update({full_address: []})
        # add new outbox to self.outboxes
        self.outboxes.update({full_address: []})
        # add new drafts box to self.drafts
        self.drafts.update({full_address: []})
        # add new trash box to self.trashes
        self.trashes.update({full_address: []})

        return agent

    async def admin_delete_agent(
        self, admin: MAILAdmin, local_address: str
    ) -> MAILAgent:
        """
        Delete an existing MAIL agent by local address (agent@swarm).
        """

        full_address = f"{local_address}@{self.host}"
        user_agent = self.user_agents.get(full_address)
        if user_agent is None:
            raise ValueError(f"agent not found: {local_address}")
        if user_agent.user_agent.ua_type != "agent":
            raise ValueError(f"invalid agent address: {local_address}")

        agent = self.user_agents.pop(full_address)
        if not isinstance(agent.user_agent, MAILAgent):
            self.user_agents.update(
                {full_address: agent}
            )  # re-add if invalid this far in
            raise ValueError(f"invalid agent address: {local_address}")

        # remove inbox from self.inboxes
        self.inboxes.pop(full_address)
        # drop any per-owner read state alongside the inbox
        self.read_inbox.pop(full_address, None)
        # remove outbox from self.outboxes
        self.outboxes.pop(full_address)
        # remove drafts box from self.drafts
        self.drafts.pop(full_address)
        # remove trash box from self.trashes
        self.trashes.pop(full_address)

        return agent.user_agent

    async def admin_get_daemons(
        self,
        admin: MAILAdmin,
    ) -> list[str]:
        """
        Get a list of daemons by worker name registered on this server.
        """

        daemons = [
            addr
            for addr, ua in self.user_agents.items()
            if ua.user_agent.ua_type == "daemon"
        ]
        worker_names: list[str] = []
        for daemon in daemons:
            name, _host = daemon.split("@")
            worker_name = name.removeprefix("daemon:")
            worker_names.append(worker_name)

        return worker_names

    async def admin_get_daemon(
        self,
        admin: MAILAdmin,
        worker_name: str,
    ) -> MAILDaemon:
        """
        Get a specific registered daemon by worker name.
        """

        full_address = f"daemon:{worker_name}@{self.host}"
        daemon = self.user_agents.get(full_address)
        if daemon is None:
            raise ValueError(f"no daemon found with worker name {worker_name}")
        if daemon.user_agent.ua_type != "daemon":
            raise ValueError(f"invalid worker name: {worker_name}")

        return daemon.user_agent

    async def admin_post_daemon(
        self,
        admin: MAILAdmin,
        payload: AdminDaemonPostRequest,
    ) -> MAILDaemon:
        """
        Create a new MAIL daemon with the specified credentials.
        """

        full_address = f"daemon:{payload.worker_name}@{self.host}"
        if self.user_agents.get(full_address):
            raise ValueError(f"daemon address already taken: {full_address}")

        daemon = MAILDaemon(
            ua_type="daemon",
            worker_name=payload.worker_name,
            host=self.host,
        )

        ua_in_be = MAILUserAgentInBackend(
            user_agent=daemon,
            hashed_password=get_password_hash(payload.daemon_password),
        )
        self.user_agents.update({full_address: ua_in_be})

        # add new inbox to self.inboxes
        self.inboxes.update({full_address: []})
        # add new outbox to self.outboxes
        self.outboxes.update({full_address: []})
        # add new drafts box to self.drafts
        self.drafts.update({full_address: []})
        # add new trash box to self.trashes
        self.trashes.update({full_address: []})

        return daemon

    async def admin_delete_daemon(
        self, admin: MAILAdmin, worker_name: str
    ) -> MAILDaemon:
        """
        Delete an existing MAIL daemon by worker name.
        """

        full_address = f"daemon:{worker_name}@{self.host}"
        user_agent = self.user_agents.get(full_address)
        if user_agent is None:
            raise ValueError(f"daemon not found: {worker_name}")
        if user_agent.user_agent.ua_type != "daemon":
            raise ValueError(f"invalid daemon worker name: {worker_name}")

        daemon = self.user_agents.pop(full_address)
        if not isinstance(daemon.user_agent, MAILDaemon):
            self.user_agents.update(
                {full_address: daemon}
            )  # re-add if invalid this far in
            raise ValueError(f"invalid daemon worker name: {worker_name}")

        # remove inbox from self.inboxes
        self.inboxes.pop(full_address)
        # drop any per-owner read state alongside the inbox
        self.read_inbox.pop(full_address, None)
        # remove outbox from self.outboxes
        self.outboxes.pop(full_address)
        # remove drafts box from self.drafts
        self.drafts.pop(full_address)
        # remove trash box from self.trashes
        self.trashes.pop(full_address)

        return daemon.user_agent

    async def admin_get_users(
        self,
        admin: MAILAdmin,
    ) -> list[str]:
        """
        Get a list of users by user ID registed on this server.
        """

        users = [
            addr
            for addr, ua in self.user_agents.items()
            if ua.user_agent.ua_type == "user"
        ]
        user_ids: list[str] = []
        for user in users:
            name, _host = user.split("@")
            user_id = name.removeprefix("user:")
            user_ids.append(user_id)

        return user_ids

    async def admin_get_user(
        self,
        admin: MAILAdmin,
        user_id: str,
    ) -> MAILUser:
        """
        Get a specific registered user by user ID.
        """

        full_address = f"user:{user_id}@{self.host}"
        user = self.user_agents.get(full_address)
        if user is None:
            raise ValueError(f"no user found with ID {user_id}")
        if user.user_agent.ua_type != "user":
            raise ValueError(f"invalid user ID: {user_id}")

        return user.user_agent

    async def admin_post_user(
        self,
        admin: MAILAdmin,
        payload: AdminUserPostRequest,
    ) -> MAILUser:
        """
        Create a new MAIL user with the specified credentials.
        """

        full_address = f"user:{payload.user_id}@{self.host}"
        if self.user_agents.get(full_address):
            raise ValueError(f"user address already taken: {full_address}")

        user = MAILUser(
            ua_type="user",
            user_id=payload.user_id,
            host=self.host,
        )

        ua_in_be = MAILUserAgentInBackend(
            user_agent=user,
            hashed_password=get_password_hash(payload.user_password),
        )
        self.user_agents.update({full_address: ua_in_be})

        # add new inbox to self.inboxes
        self.inboxes.update({full_address: []})
        # add new outbox to self.outboxes
        self.outboxes.update({full_address: []})
        # add new drafts box to self.drafts
        self.drafts.update({full_address: []})
        # add new trash box to self.trashes
        self.trashes.update({full_address: []})

        return user

    async def admin_delete_user(self, admin: MAILAdmin, user_id: str) -> MAILUser:
        """
        Delete an existing MAIL user by user ID.
        """

        full_address = f"user:{user_id}@{self.host}"
        user_agent = self.user_agents.get(full_address)
        if user_agent is None:
            raise ValueError(f"user not found: {user_id}")
        if user_agent.user_agent.ua_type != "user":
            raise ValueError(f"invalid user ID: {user_id}")

        user = self.user_agents.pop(full_address)
        if not isinstance(user.user_agent, MAILUser):
            self.user_agents.update(
                {full_address: user}
            )  # re-add if invalid this far in
            raise ValueError(f"invalid user ID: {user_id}")

        # remove inbox from self.inboxes
        self.inboxes.pop(full_address)
        # drop any per-owner read state alongside the inbox
        self.read_inbox.pop(full_address, None)
        # remove outbox from self.outboxes
        self.outboxes.pop(full_address)
        # remove drafts box from self.drafts
        self.drafts.pop(full_address)
        # remove trash box from self.trashes
        self.trashes.pop(full_address)

        return user.user_agent

    async def admin_post_swarm(
        self,
        admin: MAILAdmin,
        payload: AdminSwarmPostRequest,
    ) -> MAILSwarm:
        """
        Create a new MAIL swarm on this server.
        """

        swarm_name = payload.name
        existing_swarm = self.swarms.get(swarm_name)
        if existing_swarm is not None:
            raise ValueError(f"swarm with name {swarm_name} already exists")

        new_swarm = MAILSwarm(
            name=swarm_name,
            description=payload.description,
            keywords=payload.keywords,
            agents=[],
            metadata={},
        )

        self.swarms.update({swarm_name: new_swarm})

        return new_swarm

    async def admin_delete_swarm(
        self,
        admin: MAILAdmin,
        swarm_name: str,
    ) -> MAILSwarm:
        """
        Delete an existing MAIL swarm on this server by name.
        """

        existing_swarm = self.swarms.get(swarm_name)
        if existing_swarm is None:
            raise ValueError(f"swarm with name {swarm_name} not found")

        swarm = self.swarms.pop(swarm_name)
        return swarm

    #
    # Webhook handlers
    #
    async def admin_webhooks_get(self, admin: MAILAdmin) -> list[str]:
        """
        Get the IDs for all existing server webhooks.
        """

        webhooks = self.webhooks
        return [wh.webhook_id for wh in webhooks.values()]

    async def admin_webhook_get(self, admin: MAILAdmin, webhook_id: str) -> MAILWebhook:
        """
        Get an existing server webhook by ID.
        """

        for webhook in self.webhooks.values():
            if webhook.webhook_id == webhook_id:
                return webhook

        raise ValueError(f"webhook with ID {webhook_id} not found")

    async def admin_webhook_post(
        self,
        admin: MAILAdmin,
        payload: AdminWebhooksPostRequest,
    ) -> MAILWebhook:
        """
        Create a new server webhook.
        """

        # if the given URL is already being used, return that without adding anything
        webhook = self.webhooks.get(payload.url)
        if webhook is not None:
            return webhook

        webhook_id = f"wh_{str(uuid.uuid4())}"
        new_webhook = MAILWebhook(
            webhook_id=webhook_id,
            url=payload.url,
            events=payload.events,
            secret=payload.secret,
        )
        self.webhooks.update({payload.url: new_webhook})

        return new_webhook

    async def admin_webhook_patch(
        self,
        admin: MAILAdmin,
        webhook_id: str,
        payload: AdminWebhooksPatchRequest,
    ) -> MAILWebhook:
        """
        Update an existing server webhook URL and/or secret.
        """

        raise NotImplementedError

    async def admin_webhook_delete(
        self,
        admin: MAILAdmin,
        webhook_id: str,
    ) -> MAILWebhook:
        """
        Delete an existing server webhook by ID.
        """

        wh_url: str | None = None
        for webhook in self.webhooks.values():
            if webhook.webhook_id == webhook_id:
                wh_url = webhook.url
                break

        if wh_url is None:
            raise ValueError(f"webhook with ID {webhook_id} not found")

        return self.webhooks.pop(wh_url)

    async def _handle_webhook_delivered(
        self,
        recipient: str,
        message: MAILMessage,
        list_address: str | None = None,
    ) -> None:
        """
        Handle all `mail.delivered` webhooks.

        Webhooks are only fired for *agent* recipients —
        ``name@swarm@host`` shaped addresses. Non-agent recipients
        (users, admins, daemons; addresses like ``admin:ryan@chrn.ai``)
        don't have a downstream conduit listener; they read mail via
        MAIL's CLI/UI directly. Firing for them also crashes inside
        ``_webhook_delivered_post`` because the payload's ``swarm`` is
        derived from ``recipient.split("@")[1]``, which is the host
        for a 2-segment address and fails ``validate_swarm_name``.

        ``list_address`` is set when the delivery originated from a
        list expansion; the webhook receiver uses it to surface the
        originating list to the recipient.
        """

        if not _is_agent_recipient(recipient):
            return

        for url, webhook in self.webhooks.items():
            if "mail.delivered" in webhook.events:
                _task = asyncio.create_task(
                    self.handle_webhook_delivered_for_url(
                        url=url,
                        recipient=recipient,
                        message=message,
                        secret=webhook.secret,
                        list_address=list_address,
                    )
                )

    async def _deliver_to_address(
        self,
        *,
        address: str,
        inbox_entry: MAILInboxEntrySummary,
        message: MAILMessage,
        list_address: str | None,
    ) -> None:
        """
        Deliver one inbox entry to a single recipient.

        Validates the recipient address against the registered
        user-agents, appends the inbox-entry id to that recipient's
        inbox list, and fires ``mail.delivered`` webhooks (agent
        recipients only). Unknown recipients are logged and skipped
        rather than aborting the wider delivery.
        """

        try:
            user_agent = await self.get_user_agent(address)
            ua_address = user_agent.get_address()
        except Exception:
            logger.warning(f"failed to validate recipient address {address}")
            return

        self.inboxes[ua_address].append(inbox_entry.message_id)

        # `mail.delivered` webhooks are agent-scoped at v1: the payload's
        # required swarm field only exists for swarm-scoped addresses.
        # Host-scoped recipients (user:/admin:/daemon:) receive mail
        # without firing webhooks.
        if user_agent.user_agent.ua_type != "agent":
            logger.debug(
                f"skipping `mail.delivered` webhooks for non-agent recipient {address}"
            )
            return

        await self._handle_webhook_delivered(
            recipient=address,
            message=message,
            list_address=list_address,
        )

    async def _fan_out_to_list(
        self,
        *,
        list_address: str,
        inbox_entry: MAILInboxEntrySummary,
        message: MAILMessage,
    ) -> None:
        """
        Expand a ``list:`` recipient into per-member deliveries.

        Looks the list up, iterates members, delivers to each via
        ``_deliver_to_address`` with ``list_address`` populated so the
        per-member webhook events can carry the originating list.

        Lists that aren't present on the server are logged and
        skipped; nested list members (another ``list:`` prefix) are
        rejected to keep v1 fan-out single-hop.
        """

        try:
            mail_list = await self.get_list(list_address)
        except ValueError:
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
                address=member,
                inbox_entry=inbox_entry,
                message=message,
                list_address=list_address,
            )

    #
    # List endpoints
    #
    async def get_lists(self) -> list[MAILListInBackend]:
        """
        Get all MAIL lists known to this server (no auth scope).
        """

        return list(self.lists.values())

    async def get_list(self, list_address: str) -> MAILListInBackend:
        """
        Get a specific MAIL list by its ``list:`` address (no auth scope).
        """

        mail_list = self.lists.get(list_address)
        if mail_list is None:
            raise ValueError(f"list not found: {list_address}")
        return mail_list

    async def admin_get_lists(self, admin: MAILAdmin) -> list[MAILListInBackend]:
        """
        Admin read of every list known to the server.
        """

        return await self.get_lists()

    async def admin_get_list(
        self,
        admin: MAILAdmin,
        list_address: str,
    ) -> MAILListInBackend:
        """
        Admin read of a specific MAIL list.
        """

        return await self.get_list(list_address)

    async def admin_post_list(
        self,
        admin: MAILAdmin,
        payload: AdminListPostRequest,
    ) -> MAILListInBackend:
        """
        Create a new MAIL list on this server.
        """

        mail_list = MAILList(
            name=payload.name,
            swarm=payload.swarm_name,
            host=self.host,
            owner=payload.owner,
            members=payload.members,
            policy=payload.policy,
        )
        address = mail_list.get_address()
        if address in self.lists:
            raise ValueError(f"list address already taken: {address}")

        now = datetime.now(UTC)
        record = MAILListInBackend(
            **mail_list.model_dump(),
            list_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
        )
        self.lists[address] = record
        return record

    async def admin_patch_list(
        self,
        admin: MAILAdmin,
        list_address: str,
        payload: AdminListPatchRequest,
    ) -> MAILListInBackend:
        """
        Update mutable fields on an existing MAIL list. v1 only supports
        policy edits; the canonical address (name, swarm, host) is
        immutable for the life of the list.
        """

        existing = self.lists.get(list_address)
        if existing is None:
            raise ValueError(f"list not found: {list_address}")

        updated_fields: dict[str, Any] = {}
        if payload.policy is not None:
            updated_fields["policy"] = payload.policy

        if updated_fields:
            updated = existing.model_copy(
                update={**updated_fields, "updated_at": datetime.now(UTC)}
            )
            self.lists[list_address] = updated
            return updated
        return existing

    async def admin_delete_list(
        self,
        admin: MAILAdmin,
        list_address: str,
    ) -> MAILListInBackend:
        """
        Delete an existing MAIL list by its full ``list:`` address.
        """

        existing = self.lists.get(list_address)
        if existing is None:
            raise ValueError(f"list not found: {list_address}")
        return self.lists.pop(list_address)

    async def add_list_member(
        self,
        list_address: str,
        member_address: str,
    ) -> MAILListInBackend:
        """
        Append a member to a MAIL list.

        Idempotent — re-adding an existing member returns the list
        unchanged. Permission checks (against the list's ``join_policy``)
        are the responsibility of the calling router; the storage layer
        does not enforce them.
        """

        existing = self.lists.get(list_address)
        if existing is None:
            raise ValueError(f"list not found: {list_address}")
        if member_address in existing.members:
            return existing

        updated_members = [*existing.members, member_address]
        updated = existing.model_copy(
            update={"members": updated_members, "updated_at": datetime.now(UTC)}
        )
        self.lists[list_address] = updated
        return updated

    async def remove_list_member(
        self,
        list_address: str,
        member_address: str,
    ) -> MAILListInBackend:
        """
        Remove a member from a MAIL list.

        Idempotent — removing a non-member returns the list unchanged.
        """

        existing = self.lists.get(list_address)
        if existing is None:
            raise ValueError(f"list not found: {list_address}")
        if member_address not in existing.members:
            return existing

        updated_members = [m for m in existing.members if m != member_address]
        updated = existing.model_copy(
            update={"members": updated_members, "updated_at": datetime.now(UTC)}
        )
        self.lists[list_address] = updated
        return updated

    #
    # Message endpoints
    #
    async def get_message(self, message_id: str) -> MAILMessage:
        """
        Attempt to get a locally-defined MAIL message by ID.
        """

        message = self.messages.get(message_id)
        if message is None:
            raise ValueError(f"undefined message ID: {message_id}")

        return message
