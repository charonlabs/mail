# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import logging
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from mail_protocol.core.drafts import MAILDraft, MAILDraftsEntry, MAILDraftsEntrySummary
from mail_protocol.core.inbox import MAILInboxEntry, MAILInboxEntrySummary
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
from mail_protocol.network.requests import (
    AdminAgentPostRequest,
    AdminDaemonPostRequest,
    AdminSwarmPostRequest,
    AdminUserPostRequest,
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
    load_message_buffer,
    load_messages,
    load_outbox_entries,
    load_outboxes,
    load_swarms,
    load_trash_entries,
    load_trashes,
    load_user_agents,
    save_draft_entries,
    save_drafts,
    save_inbox_entries,
    save_inboxes,
    save_message_buffer,
    save_messages,
    save_outbox_entries,
    save_outboxes,
    save_swarms,
    save_trash_entries,
    save_trashes,
    save_user_agents,
)

logger = logging.getLogger(__name__)


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

            # 3. update the inbox of each recipient
            recipients = message.recipients
            for rec in recipients:
                try:
                    user_agent = await self.get_user_agent(rec)
                    ua_address = user_agent.get_address()
                except Exception:
                    logger.warning(f"failed to validate recipient address {rec}")
                    continue

                self.inboxes[ua_address].append(inbox_entry.message_id)

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
