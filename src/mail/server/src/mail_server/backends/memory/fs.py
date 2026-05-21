# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from os import scandir
from pathlib import Path

from mail_protocol.core.drafts import MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.queues import MAILQueueEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILAgent, MAILUserAgentInBackend
from mail_protocol.core.validators import (
    validate_mail_address,
    validate_swarm_name,
    validate_uuid,
    validate_uuids,
)

DEPLOYMENT_PATH = Path.home().joinpath(".mail-swarms", "deployments", "default")


#
# Load memory backend from the local filesystem
# (on server startup)
#
async def load_user_agents() -> dict[str, MAILUserAgentInBackend]:
    """
    Load saved user-agents from the local filesystem.
    """

    user_agents_path = DEPLOYMENT_PATH.joinpath("user_agents")
    user_agents: dict[str, MAILUserAgentInBackend] = {}
    with scandir(user_agents_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError:
                    continue

                with open(entry) as ua_file:
                    content = ua_file.read()
                    try:
                        ua_model = MAILUserAgentInBackend.model_validate_json(content)
                    except Exception:
                        continue

                    user_agents.update({ua_model.get_address(): ua_model})

    return user_agents


async def load_swarms() -> dict[str, MAILSwarm]:
    """
    Load saved MAIL swarms from the local filesystem.
    """

    swarms_path = DEPLOYMENT_PATH.joinpath("swarms")
    swarms: dict[str, MAILSwarm] = {}
    with scandir(swarms_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_swarm_name(entry.name)
                except ValueError:
                    continue

                with open(entry) as swarm_file:
                    content = swarm_file.read()
                    try:
                        swarm_model = MAILSwarm.model_validate_json(content)
                    except Exception:
                        continue

                    swarms.update({swarm_model.name: swarm_model})

    return swarms


async def load_messages() -> dict[str, MAILMessage]:
    """
    Load saved MAIL messages from the local filesystem.
    """

    messages_path = DEPLOYMENT_PATH.joinpath("messages")
    messages: dict[str, MAILMessage] = {}
    with scandir(messages_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError:
                    continue

                with open(entry) as message_file:
                    content = message_file.read()
                    try:
                        message_model = MAILMessage.model_validate_json(content)
                    except Exception:
                        continue

                    messages.update({message_model.message_id: message_model})

    return messages


async def load_inbox_entries() -> dict[str, MAILInboxEntrySummary]:
    """
    Load saved inbox entries from the local filesystem.
    """

    inbox_entries_path = DEPLOYMENT_PATH.joinpath("inbox_entries")
    inbox_entries: dict[str, MAILInboxEntrySummary] = {}
    with scandir(inbox_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError:
                    continue

                with open(entry) as ie_file:
                    content = ie_file.read()
                    try:
                        ie_model = MAILInboxEntrySummary.model_validate_json(content)
                    except Exception:
                        continue

                    inbox_entries.update({ie_model.message_id: ie_model})

    return inbox_entries


async def load_inboxes() -> dict[str, list[str]]:
    """
    Load saved user-agent inboxes from the local filesystem.
    """

    inboxes_path = DEPLOYMENT_PATH.joinpath("inboxes")
    inboxes: dict[str, list[str]] = {}
    with scandir(inboxes_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError:
                    continue

                with open(entry) as inbox_file:
                    ie_ids = inbox_file.readlines()
                    try:
                        validate_uuids(ie_ids)
                    except ValueError:
                        continue

                    inboxes.update({entry.name: ie_ids})

    return inboxes


async def load_outbox_entries() -> dict[str, MAILOutboxEntrySummary]:
    """
    Load saved outbox entries from the local filesystem.
    """

    outbox_entries_path = DEPLOYMENT_PATH.joinpath("outbox_entries")
    outbox_entries: dict[str, MAILOutboxEntrySummary] = {}
    with scandir(outbox_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError:
                    continue

                with open(entry) as oe_file:
                    content = oe_file.read()
                    try:
                        oe_model = MAILOutboxEntrySummary.model_validate_json(content)
                    except Exception:
                        continue

                    outbox_entries.update({oe_model.message_id: oe_model})

    return outbox_entries


async def load_outboxes() -> dict[str, list[str]]:
    """
    Load saved user-agent outboxes from the local filesystem.
    """

    outboxes_path = DEPLOYMENT_PATH.joinpath("outboxes")
    outboxes: dict[str, list[str]] = {}
    with scandir(outboxes_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError:
                    continue

                with open(entry) as outbox_file:
                    oe_ids = outbox_file.readlines()
                    try:
                        validate_uuids(oe_ids)
                    except ValueError:
                        continue

                    outboxes.update({entry.name: oe_ids})

    return outboxes


async def load_draft_entries() -> dict[str, MAILDraftsEntry]:
    """
    Load saved draft box entries from the local filesystem.
    """

    draft_entries_path = DEPLOYMENT_PATH.joinpath("draft_entries")
    draft_entries: dict[str, MAILDraftsEntry] = {}
    with scandir(draft_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError:
                    continue

                with open(entry) as de_file:
                    content = de_file.read()
                    try:
                        de_model = MAILDraftsEntry.model_validate_json(content)
                    except Exception:
                        continue

                    draft_entries.update({de_model.draft.draft_id: de_model})

    return draft_entries


async def load_drafts() -> dict[str, list[str]]:
    """
    Load saved user-agent draft boxes from the local filesystem.
    """

    drafts_path = DEPLOYMENT_PATH.joinpath("drafts")
    drafts: dict[str, list[str]] = {}
    with scandir(drafts_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError:
                    continue

                with open(entry) as drafts_file:
                    draft_ids = drafts_file.readlines()
                    try:
                        validate_uuids(draft_ids)
                    except ValueError:
                        continue

                    drafts.update({entry.name: draft_ids})

    return drafts


async def load_trash_entries() -> dict[str, MAILTrashEntry]:
    """
    Load saved trash box entries from the local filesystem.
    """

    trash_entries_path = DEPLOYMENT_PATH.joinpath("trash_entries")
    trash_entries: dict[str, MAILTrashEntry] = {}
    with scandir(trash_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError:
                    continue

                with open(entry) as te_file:
                    content = te_file.read()
                    try:
                        te_model = MAILTrashEntry.model_validate_json(content)
                    except Exception:
                        continue

                    trash_entries.update({te_model.message.message_id: te_model})

    return trash_entries


async def load_trashes() -> dict[str, list[str]]:
    """
    Load saved user-agent trash boxes from the local filesystem.
    """

    trashes_path = DEPLOYMENT_PATH.joinpath("trashes")
    trashes: dict[str, list[str]] = {}
    with scandir(trashes_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError:
                    continue

                with open(entry) as trash_file:
                    trash_ids = trash_file.readlines()
                    try:
                        validate_uuids(trash_ids)
                    except ValueError:
                        continue

                    trashes.update({entry.name: trash_ids})

    return trashes


async def load_delivery_queue() -> dict[str, MAILQueueEntrySummary]:
    """
    Load saved message delivery queue from the local filesystem.
    """

    delivery_queue_path = DEPLOYMENT_PATH.joinpath("delivery_queue")
    delivery_queue: dict[str, MAILQueueEntrySummary] = {}
    with scandir(delivery_queue_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError:
                    continue

                with open(entry) as dq_file:
                    content = dq_file.read()
                    try:
                        dq_model = MAILQueueEntrySummary.model_validate_json(content)
                    except Exception:
                        continue

                    delivery_queue.update({dq_model.message_id: dq_model})

    return delivery_queue


#
# Save memory backend to the local filesystem
# (on server shutdown)
#
async def save_user_agents(user_agents: dict[str, MAILUserAgentInBackend]) -> None:
    """
    Save user-agents from memory to the local filesystem.
    """

    user_agents_path = DEPLOYMENT_PATH.joinpath("user_agents")
    for address, user_agent in user_agents.items():
        ua_path = user_agents_path.joinpath(address)
        with open(ua_path, "w") as ua_file:
            content = user_agent.model_dump_json()
            ua_file.write(content)


async def save_swarms(swarms: dict[str, MAILSwarm]) -> None:
    """
    Save MAIL swarms from memory to the local filesystem.
    """

    swarms_path = DEPLOYMENT_PATH.joinpath("swarms")
    for name, swarm in swarms.items():
        swarm_path = swarms_path.joinpath(name)
        with open(swarm_path, "w") as swarm_file:
            content = swarm.model_dump_json()
            swarm_file.write(content)


async def save_messages(messages: dict[str, MAILMessage]) -> None:
    """
    Save MAIL messages from memory to the local filesystem.
    """

    messages_path = DEPLOYMENT_PATH.joinpath("messages")
    for msg_id, message in messages.items():
        msg_path = messages_path.joinpath(msg_id)
        with open(msg_path, "w") as msg_file:
            content = message.model_dump_json()
            msg_file.write(content)


async def save_inbox_entries(inbox_entries: dict[str, MAILInboxEntrySummary]) -> None:
    """
    Save inbox entries from memory to the local filesystem.
    """

    inbox_entries_path = DEPLOYMENT_PATH.joinpath("inbox_entries")
    for msg_id, inbox_entry in inbox_entries.items():
        ie_path = inbox_entries_path.joinpath(msg_id)
        with open(ie_path, "w") as ie_file:
            content = inbox_entry.model_dump_json()
            ie_file.write(content)


async def save_inboxes(inboxes: dict[str, list[str]]) -> None:
    """
    Save user-agent inboxes from memory to the local filesystem.
    """

    inboxes_path = DEPLOYMENT_PATH.joinpath("inboxes")
    for address, ie_ids in inboxes.items():
        inbox_path = inboxes_path.joinpath(address)
        with open(inbox_path, "w") as inbox_file:
            content = "\n".join(ie_ids)
            inbox_file.write(content)


async def save_outbox_entries(
    outbox_entries: dict[str, MAILOutboxEntrySummary],
) -> None:
    """
    Save outbox entries from memory to the local filesystem.
    """

    outbox_entries_path = DEPLOYMENT_PATH.joinpath("outbox_entries")
    for msg_id, outbox_entry in outbox_entries.items():
        oe_path = outbox_entries_path.joinpath(msg_id)
        with open(oe_path, "w") as oe_file:
            content = outbox_entry.model_dump_json()
            oe_file.write(content)


async def save_outboxes(outboxes: dict[str, list[str]]) -> None:
    """
    Save user-agent outboxes from memory to the local filesystem.
    """

    outboxes_path = DEPLOYMENT_PATH.joinpath("outboxes")
    for address, oe_ids in outboxes.items():
        outbox_path = outboxes_path.joinpath(address)
        with open(outbox_path, "w") as outbox_file:
            content = "\n".join(oe_ids)
            outbox_file.write(content)


async def save_draft_entries(
    draft_entries: dict[str, MAILDraftsEntry],
) -> None:
    """
    Save draft entries from memory to the local filesystem.
    """

    draft_entries_path = DEPLOYMENT_PATH.joinpath("draft_entries")
    for draft_id, draft_entry in draft_entries.items():
        de_path = draft_entries_path.joinpath(draft_id)
        with open(de_path, "w") as de_file:
            content = draft_entry.model_dump_json()
            de_file.write(content)


async def save_drafts(drafts: dict[str, list[str]]) -> None:
    """
    Save user-agent draft boxes from memory to the local filesystem.
    """

    draft_boxes_path = DEPLOYMENT_PATH.joinpath("drafts")
    for address, draft_ids in drafts.items():
        drafts_path = draft_boxes_path.joinpath(address)
        with open(drafts_path, "w") as drafts_file:
            content = "\n".join(draft_ids)
            drafts_file.write(content)


async def save_trash_entries(trash_entries: dict[str, MAILTrashEntry]) -> None:
    """
    Save trash entries from memory to the local filesystem.
    """

    trash_entries_path = DEPLOYMENT_PATH.joinpath("trash_entries")
    for msg_id, trash_entry in trash_entries.items():
        te_path = trash_entries_path.joinpath(msg_id)
        with open(te_path, "w") as te_file:
            content = trash_entry.model_dump_json()
            te_file.write(content)


async def save_trashes(trashes: dict[str, list[str]]) -> None:
    """
    Save user-agent trash boxes from memory to the local filesystem.
    """

    trash_boxes_path = DEPLOYMENT_PATH.joinpath("trashes")
    for address, te_ids in trashes.items():
        trash_path = trash_boxes_path.joinpath(address)
        with open(trash_path, "w") as trash_file:
            content = "\n".join(te_ids)
            trash_file.write(content)


async def save_delivery_queue(delivery_queue: dict[str, MAILQueueEntrySummary]) -> None:
    """
    Save message delivery queue from memory to the local filesystem.
    """

    queue_entries_path = DEPLOYMENT_PATH.joinpath("queue_entries")
    for msg_id, queue_entry in delivery_queue.items():
        qe_path = queue_entries_path.joinpath(msg_id)
        with open(qe_path, "w") as qe_file:
            content = queue_entry.model_dump_json()
            qe_file.write(content)
