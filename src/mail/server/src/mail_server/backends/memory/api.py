# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import asyncio
import logging
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

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
    DaemonDeliverLocalRequest,
    DaemonDeliverRemoteRequest,
    DraftPostRequest,
    DraftSendPostRequest,
)

from mail_server.auth import get_password_hash, verify_password
from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.fs import (
    load_draft_entries,
    load_drafts,
    load_inbox_entries,
    load_inboxes,
    load_lists,
    load_message_buffer,
    load_messages,
    load_outbox_entries,
    load_outboxes,
    load_swarms,
    load_trash_entries,
    load_trashes,
    load_user_agents,
    load_webhooks,
    save_draft_entries,
    save_drafts,
    save_inbox_entries,
    save_inboxes,
    save_lists,
    save_message_buffer,
    save_messages,
    save_outbox_entries,
    save_outboxes,
    save_swarms,
    save_trash_entries,
    save_trashes,
    save_user_agents,
    save_webhooks,
)

logger = logging.getLogger(__name__)


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

        host = kwargs.get("host")
        if host is not None:
            if isinstance(host, str):
                self.host = host

        logger.info("backend initialization complete")

    async def on_server_shutdown(self, **kwargs: Any) -> None:
        """
        Handle backend events on server shutdown.
        """

        logger.info("shutting down backend...")

        await save_user_agents(self.user_agents)
        await save_swarms(self.swarms)
        await save_messages(self.messages)
        await save_inbox_entries(self.inbox_entries)
        await save_inboxes(self.inboxes)
        await save_outbox_entries(self.outbox_entries)
        await save_outboxes(self.outboxes)
        await save_draft_entries(self.draft_entries)
        await save_drafts(self.drafts)
        await save_trash_entries(self.trash_entries)
        await save_trashes(self.trashes)
        await save_message_buffer(self.message_buffer)
        await save_webhooks(self.webhooks)
        await save_lists(self.lists)

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
        message = MAILMessage(
            message_id=message_id,
            sender=ua_address,
            recipients=payload.recipients,
            subject=draft.subject,
            body=draft.body,
            sent_at=datetime.now(UTC),
            metadata={},
        )
        outbox_entry = MAILOutboxEntrySummary(
            message_id=message_id,
            recipients=message.recipients,
            subject=message.subject,
            body_size=len(message.body),
            sent_at=datetime.now(UTC),
            delivered_at=None,
            delivered_by=None,
        )

        # add to server messages
        self.messages.update({message_id: message})
        # add to server outbox_entries
        self.outbox_entries.update({message_id: outbox_entry})
        # add to user-agent's outbox
        self.outboxes[ua_address].append(message_id)
        # add to message delivery buffer
        self.message_buffer.append(message_id)

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

        return message_buffer

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

            # 1. update shared outbox entry
            outbox_entry = self.outbox_entries[message.message_id]
            outbox_entry.delivered_at = delivered_time
            outbox_entry.delivered_by = daemon.get_address()
            self.outbox_entries.update({message.message_id: outbox_entry})

            # 2. create shared inbox entry
            inbox_entry = MAILInboxEntrySummary(
                message_id=message.message_id,
                sender=message.sender,
                subject=message.subject,
                body_size=len(message.body),
                received_at=delivered_time,
                delivered_by=daemon.get_address(),
            )
            self.inbox_entries.update({inbox_entry.message_id: inbox_entry})

            # 3. update the inbox of each recipient. Recipients with the
            # ``list:`` prefix are fan-out targets; expand to members,
            # deliver to each, and tag the per-member webhook with the
            # originating list address. Direct recipients are delivered
            # as before with no list tag.
            for rec in message.recipients:
                if rec.startswith(f"{LIST_ADDRESS_PREFIX}:"):
                    await self._fan_out_to_list(
                        list_address=rec,
                        inbox_entry=inbox_entry,
                        message=message,
                    )
                    continue
                await self._deliver_to_address(
                    address=rec,
                    inbox_entry=inbox_entry,
                    message=message,
                    list_address=None,
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
        agent_address: str,
    ) -> MAILAgent:
        """
        Get a specific registered agent by local address (agent@swarm).
        """

        full_address = f"{agent_address}@{self.host}"
        agent = self.user_agents.get(full_address)
        if agent is None:
            raise ValueError(f"no agent found with address {agent_address}")
        if agent.user_agent.ua_type != "agent":
            raise ValueError(f"invalid agent address: {agent_address}")

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
        self, admin: MAILAdmin, agent_address: str
    ) -> MAILAgent:
        """
        Delete an existing MAIL agent by local address (agent@swarm).
        """

        full_address = f"{agent_address}@{self.host}"
        user_agent = self.user_agents.get(full_address)
        if user_agent is None:
            raise ValueError(f"agent not found: {agent_address}")
        if user_agent.user_agent.ua_type != "agent":
            raise ValueError(f"invalid agent address: {agent_address}")

        agent = self.user_agents.pop(full_address)
        if not isinstance(agent.user_agent, MAILAgent):
            self.user_agents.update(
                {full_address: agent}
            )  # re-add if invalid this far in
            raise ValueError(f"invalid agent address: {agent_address}")

        # remove inbox from self.inboxes
        self.inboxes.pop(full_address)
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
                f"skipping `mail.delivered` webhooks for non-agent "
                f"recipient {address}"
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
