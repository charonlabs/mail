# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import logging
import os
import tempfile
from os import scandir
from pathlib import Path

from mail_protocol.core.auth import RefreshTokenRecord
from mail_protocol.core.drafts import MAILDraftsEntry
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.lists import MAILListInBackend
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILUserAgentInBackend
from mail_protocol.core.validators import (
    validate_mail_address,
    validate_swarm_name,
    validate_uuid,
    validate_webhook_id,
)
from mail_protocol.core.webhooks import MAILWebhook

logger = logging.getLogger(__name__)

DEPLOYMENT_PATH = Path.home().joinpath(".mail-swarms", "deployments", "default")


def _fsync_dir(path: Path) -> None:
    """
    Best-effort fsync for a directory after atomic file replacement.
    """

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY

    try:
        fd = os.open(path, flags)
    except OSError:
        return

    try:
        os.fsync(fd)
    except OSError:
        logger.debug("failed to fsync directory %s", path, exc_info=True)
    finally:
        os.close(fd)


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Atomically replace ``path`` with ``content``.

    The temporary file is created in the same directory so ``os.replace`` is an
    atomic rename on the target filesystem.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.debug("failed to remove temporary file %s", tmp_path, exc_info=True)
        raise


def _remove_stale_files(directory: Path, expected_names: set[str]) -> None:
    """
    Remove files in ``directory`` that are no longer present in a snapshot.
    """

    removed = False
    with scandir(directory) as entries:
        for entry in entries:
            if entry.is_file() and entry.name not in expected_names:
                Path(entry.path).unlink()
                removed = True

    if removed:
        _fsync_dir(directory)


def _save_directory_snapshot(directory: Path, files: dict[str, str]) -> None:
    """
    Save a complete directory-backed collection snapshot.
    """

    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        _atomic_write_text(directory.joinpath(name), content)
    _remove_stale_files(directory, set(files))


#
# Load memory backend from the local filesystem
# (on server startup)
#
async def load_user_agents() -> dict[str, MAILUserAgentInBackend]:
    """
    Load saved user-agents from the local filesystem.
    """

    user_agents_path = DEPLOYMENT_PATH.joinpath("user_agents")
    logger.info(f"loading user_agents: {user_agents_path}...")
    user_agents: dict[str, MAILUserAgentInBackend] = {}
    with scandir(user_agents_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError as e:
                    logger.info(f"failed to validate MAIL address: {e}")
                    continue

                with open(entry) as ua_file:
                    content = ua_file.read()
                    try:
                        ua_model = MAILUserAgentInBackend.model_validate_json(content)
                    except Exception as e:
                        logger.info(f"model validation failed: {e}")
                        continue

                    user_agents.update({ua_model.get_address(): ua_model})

    logger.info(f"found {len(user_agents)} user_agents")

    return user_agents


async def load_swarms() -> dict[str, MAILSwarm]:
    """
    Load saved MAIL swarms from the local filesystem.
    """

    swarms_path = DEPLOYMENT_PATH.joinpath("swarms")
    logger.info(f"loading swarms: {swarms_path}...")
    swarms: dict[str, MAILSwarm] = {}
    with scandir(swarms_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_swarm_name(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL swarm name validation failed: {e}")
                    continue

                with open(entry) as swarm_file:
                    content = swarm_file.read()
                    try:
                        swarm_model = MAILSwarm.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"MAILSwarm model validation failed: {e}")
                        continue

                    swarms.update({swarm_model.name: swarm_model})

    logger.info(f"found {len(swarms)} swarms")

    return swarms


async def load_messages() -> dict[str, MAILMessage]:
    """
    Load saved MAIL messages from the local filesystem.
    """

    messages_path = DEPLOYMENT_PATH.joinpath("messages")
    logger.info(f"loading messages: {messages_path}...")
    messages: dict[str, MAILMessage] = {}
    with scandir(messages_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL message ID validation failed: {e}")
                    continue

                with open(entry) as message_file:
                    content = message_file.read()
                    try:
                        message_model = MAILMessage.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"MAILMessage model validation failed: {e}")
                        continue

                    messages.update({message_model.message_id: message_model})

    logger.info(f"found {len(messages)} messages")

    return messages


async def load_inbox_entries() -> dict[str, MAILInboxEntrySummary]:
    """
    Load saved inbox entries from the local filesystem.
    """

    inbox_entries_path = DEPLOYMENT_PATH.joinpath("inbox_entries")
    logger.info(f"loading inbox_entries: {inbox_entries_path}...")
    inbox_entries: dict[str, MAILInboxEntrySummary] = {}
    with scandir(inbox_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL message ID validation failed: {e}")
                    continue

                with open(entry) as ie_file:
                    content = ie_file.read()
                    try:
                        ie_model = MAILInboxEntrySummary.model_validate_json(content)
                    except Exception as e:
                        logger.warning(
                            f"MAILInboxEntrySummary model validation failed: {e}"
                        )
                        continue

                    inbox_entries.update({ie_model.message_id: ie_model})

    logger.info(f"found {len(inbox_entries)} inbox_entries")

    return inbox_entries


async def load_inboxes() -> dict[str, list[str]]:
    """
    Load saved user-agent inboxes from the local filesystem.
    """

    inboxes_path = DEPLOYMENT_PATH.joinpath("inboxes")
    logger.info(f"loading inboxes: {inboxes_path}...")
    inboxes: dict[str, list[str]] = {}
    with scandir(inboxes_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL address validation failed: {e}")
                    continue

                with open(entry) as inbox_file:
                    content = inbox_file.readlines()
                    ie_ids: list[str] = []
                    for ln in content:
                        ie_id = ln.strip()
                        if not ie_id:
                            continue
                        try:
                            validate_uuid(ie_id)
                        except ValueError as e:
                            logger.warning(f"Message ID validation failed: {e}")
                            continue

                        ie_ids.append(ie_id)

                    inboxes.update({entry.name: ie_ids})

    logger.info(f"found {len(inboxes)} inboxes")

    return inboxes


async def load_outbox_entries() -> dict[str, MAILOutboxEntrySummary]:
    """
    Load saved outbox entries from the local filesystem.
    """

    outbox_entries_path = DEPLOYMENT_PATH.joinpath("outbox_entries")
    logger.info(f"loading outbox_entries: {outbox_entries_path}...")
    outbox_entries: dict[str, MAILOutboxEntrySummary] = {}
    with scandir(outbox_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError as e:
                    logger.warning(f"Message ID validation failed: {e}")
                    continue

                with open(entry) as oe_file:
                    content = oe_file.read()
                    try:
                        oe_model = MAILOutboxEntrySummary.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"MAILOutboxEntrySummary validation failed: {e}")
                        continue

                    outbox_entries.update({oe_model.message_id: oe_model})

    logger.info(f"found {len(outbox_entries)} outbox_entries")

    return outbox_entries


async def load_outboxes() -> dict[str, list[str]]:
    """
    Load saved user-agent outboxes from the local filesystem.
    """

    outboxes_path = DEPLOYMENT_PATH.joinpath("outboxes")
    logger.info(f"loading outboxes: {outboxes_path}...")
    outboxes: dict[str, list[str]] = {}
    with scandir(outboxes_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL address validation failed: {e}")
                    continue

                with open(entry) as outbox_file:
                    content = outbox_file.readlines()
                    oe_ids: list[str] = []
                    for ln in content:
                        oe_id = ln.strip()
                        if not oe_id:
                            continue
                        try:
                            validate_uuid(oe_id)
                        except ValueError as e:
                            logger.warning(f"Message ID validation failed: {e}")
                            continue

                        oe_ids.append(oe_id)

                    outboxes.update({entry.name: oe_ids})

    logger.info(f"found {len(outboxes)} outboxes")

    return outboxes


async def load_draft_entries() -> dict[str, MAILDraftsEntry]:
    """
    Load saved draft box entries from the local filesystem.
    """

    draft_entries_path = DEPLOYMENT_PATH.joinpath("draft_entries")
    logger.info(f"loading draft_entries: {draft_entries_path}...")
    draft_entries: dict[str, MAILDraftsEntry] = {}
    with scandir(draft_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError as e:
                    logger.warning(f"Message ID validation failed: {e}")
                    continue

                with open(entry) as de_file:
                    content = de_file.read()
                    try:
                        de_model = MAILDraftsEntry.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"MAILDraftsEntry model validation failed: {e}")
                        continue

                    draft_entries.update({de_model.draft.draft_id: de_model})

    logger.info(f"found {len(draft_entries)} draft_entries")

    return draft_entries


async def load_drafts() -> dict[str, list[str]]:
    """
    Load saved user-agent draft boxes from the local filesystem.
    """

    drafts_path = DEPLOYMENT_PATH.joinpath("drafts")
    logger.info(f"loading drafts: {drafts_path}...")
    drafts: dict[str, list[str]] = {}
    with scandir(drafts_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL address validation failed: {e}")
                    continue

                with open(entry) as drafts_file:
                    content = drafts_file.readlines()
                    draft_ids: list[str] = []
                    for ln in content:
                        draft_id = ln.strip()
                        if not draft_id:
                            continue
                        try:
                            validate_uuid(draft_id)
                        except ValueError as e:
                            logger.warning(f"Draft ID validation failed: {e}")
                            continue

                        draft_ids.append(draft_id)

                    drafts.update({entry.name: draft_ids})

    logger.info(f"found {len(drafts)} drafts")

    return drafts


async def load_trash_entries() -> dict[str, MAILTrashEntry]:
    """
    Load saved trash box entries from the local filesystem.
    """

    trash_entries_path = DEPLOYMENT_PATH.joinpath("trash_entries")
    logger.info(f"loading trash_entries: {trash_entries_path}...")
    trash_entries: dict[str, MAILTrashEntry] = {}
    with scandir(trash_entries_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_uuid(entry.name)
                except ValueError as e:
                    logger.warning(f"Message ID validation failed: {e}")
                    continue

                with open(entry) as te_file:
                    content = te_file.read()
                    try:
                        te_model = MAILTrashEntry.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"MAILTrashEntry model validation failed: {e}")
                        continue

                    trash_entries.update({te_model.message.message_id: te_model})

    logger.info(f"found {len(trash_entries)} trash_entries")

    return trash_entries


async def load_trashes() -> dict[str, list[str]]:
    """
    Load saved user-agent trash boxes from the local filesystem.
    """

    trashes_path = DEPLOYMENT_PATH.joinpath("trashes")
    logger.info(f"loading trashes: {trashes_path}...")
    trashes: dict[str, list[str]] = {}
    with scandir(trashes_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL address validation failed: {e}")
                    continue

                with open(entry) as trash_file:
                    content = trash_file.readlines()
                    trash_ids: list[str] = []
                    for ln in content:
                        trash_id = ln.strip()
                        if not trash_id:
                            continue
                        try:
                            validate_uuid(trash_id)
                        except ValueError as e:
                            logger.warning(f"Message ID validation failed: {e}")
                            continue

                        trash_ids.append(trash_id)

                    trashes.update({entry.name: trash_ids})

    logger.info(f"found {len(trashes)} trashes")

    return trashes


async def load_lists() -> dict[str, MAILListInBackend]:
    """
    Load saved MAIL lists from the local filesystem.
    """

    lists_path = DEPLOYMENT_PATH.joinpath("lists")
    logger.info(f"loading lists: {lists_path}...")
    lists: dict[str, MAILListInBackend] = {}
    with scandir(lists_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_mail_address(entry.name)
                except ValueError as e:
                    logger.info(f"failed to validate MAIL address: {e}")
                    continue

                with open(entry) as list_file:
                    content = list_file.read()
                    try:
                        list_model = MAILListInBackend.model_validate_json(content)
                    except Exception as e:
                        logger.info(f"MAILListInBackend validation failed: {e}")
                        continue

                    lists.update({list_model.get_address(): list_model})

    logger.info(f"found {len(lists)} lists")

    return lists


async def load_message_buffer() -> list[str]:
    """
    Load saved message delivery buffer from the local filesystem.
    """

    msg_buf_path = DEPLOYMENT_PATH.joinpath("message_buffer.lock")
    logger.info(f"loading message_buffer: {msg_buf_path}...")
    msg_buf: list[str] = []
    with open(msg_buf_path) as msg_buf_file:
        content = msg_buf_file.readlines()
        for ln in content:
            line = ln.strip()
            try:
                validate_uuid(line)
            except ValueError as e:
                logger.warning(f"invalid message ID in buffer: {e}")
                continue

            msg_buf.append(line)

    logger.info(f"found {len(msg_buf)} messages in delivery buffer")

    return msg_buf


async def load_webhooks() -> dict[str, MAILWebhook]:
    """
    Load saved server webhooks from the local filesystem.
    """

    webhooks_path = DEPLOYMENT_PATH.joinpath("webhooks")
    logger.info(f"loading webhooks: {webhooks_path}...")
    webhooks: dict[str, MAILWebhook] = {}
    with scandir(webhooks_path) as entries:
        for entry in entries:
            if entry.is_file():
                try:
                    validate_webhook_id(entry.name)
                except ValueError as e:
                    logger.warning(f"MAIL webhook ID validation failed: {e}")
                    continue

                with open(entry) as message_file:
                    content = message_file.read()
                    try:
                        webhook_model = MAILWebhook.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"MAILWebhook model validation failed: {e}")
                        continue

                    webhooks.update({webhook_model.url: webhook_model})

    logger.info(f"found {len(webhooks)} webhooks")

    return webhooks


async def load_refresh_tokens() -> dict[str, RefreshTokenRecord]:
    """
    Load saved refresh tokens from the local filesystem.

    The directory is created if absent so memory deployments provisioned before
    refresh-token support start cleanly. Each file is named by its token hash
    (sha256 hex) and holds the serialized ``RefreshTokenRecord``.
    """

    refresh_tokens_path = DEPLOYMENT_PATH.joinpath("refresh_tokens")
    refresh_tokens_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"loading refresh_tokens: {refresh_tokens_path}...")
    refresh_tokens: dict[str, RefreshTokenRecord] = {}
    with scandir(refresh_tokens_path) as entries:
        for entry in entries:
            if entry.is_file():
                with open(entry) as rt_file:
                    content = rt_file.read()
                    try:
                        rt_model = RefreshTokenRecord.model_validate_json(content)
                    except Exception as e:
                        logger.warning(f"RefreshTokenRecord validation failed: {e}")
                        continue

                    refresh_tokens.update({rt_model.token_hash: rt_model})

    logger.info(f"found {len(refresh_tokens)} refresh_tokens")

    return refresh_tokens


#
# Save memory backend to the local filesystem
# (on server shutdown and periodic checkpoints)
#
async def save_user_agents(user_agents: dict[str, MAILUserAgentInBackend]) -> None:
    """
    Save user-agents from memory to the local filesystem.
    """

    logger.info(f"saving {len(user_agents)} user_agents...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("user_agents"),
        {
            address: user_agent.model_dump_json()
            for address, user_agent in user_agents.items()
        },
    )


async def save_swarms(swarms: dict[str, MAILSwarm]) -> None:
    """
    Save MAIL swarms from memory to the local filesystem.
    """

    logger.info(f"saving {len(swarms)} swarms...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("swarms"),
        {name: swarm.model_dump_json() for name, swarm in swarms.items()},
    )


async def save_messages(messages: dict[str, MAILMessage]) -> None:
    """
    Save MAIL messages from memory to the local filesystem.
    """

    logger.info(f"saving {len(messages)} messages...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("messages"),
        {msg_id: message.model_dump_json() for msg_id, message in messages.items()},
    )


async def save_inbox_entries(inbox_entries: dict[str, MAILInboxEntrySummary]) -> None:
    """
    Save inbox entries from memory to the local filesystem.
    """

    logger.info(f"saving {len(inbox_entries)} inbox_entries...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("inbox_entries"),
        {
            msg_id: inbox_entry.model_dump_json()
            for msg_id, inbox_entry in inbox_entries.items()
        },
    )


async def save_inboxes(inboxes: dict[str, list[str]]) -> None:
    """
    Save user-agent inboxes from memory to the local filesystem.
    """

    logger.info(f"saving {len(inboxes)} inboxes...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("inboxes"),
        {
            address: "".join(f"{ie_id}\n" for ie_id in ie_ids)
            for address, ie_ids in inboxes.items()
        },
    )


async def save_outbox_entries(
    outbox_entries: dict[str, MAILOutboxEntrySummary],
) -> None:
    """
    Save outbox entries from memory to the local filesystem.
    """

    logger.info(f"saving {len(outbox_entries)} outbox_entries...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("outbox_entries"),
        {
            msg_id: outbox_entry.model_dump_json()
            for msg_id, outbox_entry in outbox_entries.items()
        },
    )


async def save_outboxes(outboxes: dict[str, list[str]]) -> None:
    """
    Save user-agent outboxes from memory to the local filesystem.
    """

    logger.info(f"saving {len(outboxes)} outboxes...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("outboxes"),
        {
            address: "".join(f"{oe_id}\n" for oe_id in oe_ids)
            for address, oe_ids in outboxes.items()
        },
    )


async def save_draft_entries(
    draft_entries: dict[str, MAILDraftsEntry],
) -> None:
    """
    Save draft entries from memory to the local filesystem.
    """

    logger.info(f"saving {len(draft_entries)} draft_entries...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("draft_entries"),
        {
            draft_id: draft_entry.model_dump_json()
            for draft_id, draft_entry in draft_entries.items()
        },
    )


async def save_drafts(drafts: dict[str, list[str]]) -> None:
    """
    Save user-agent draft boxes from memory to the local filesystem.
    """

    logger.info(f"saving {len(drafts)} drafts...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("drafts"),
        {
            address: "".join(f"{draft_id}\n" for draft_id in draft_ids)
            for address, draft_ids in drafts.items()
        },
    )


async def save_trash_entries(trash_entries: dict[str, MAILTrashEntry]) -> None:
    """
    Save trash entries from memory to the local filesystem.
    """

    logger.info(f"saving {len(trash_entries)} trash_entries...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("trash_entries"),
        {
            msg_id: trash_entry.model_dump_json()
            for msg_id, trash_entry in trash_entries.items()
        },
    )


async def save_trashes(trashes: dict[str, list[str]]) -> None:
    """
    Save user-agent trash boxes from memory to the local filesystem.
    """

    logger.info(f"saving {len(trashes)} trashes...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("trashes"),
        {
            address: "".join(f"{te_id}\n" for te_id in te_ids)
            for address, te_ids in trashes.items()
        },
    )


async def save_lists(lists: dict[str, MAILListInBackend]) -> None:
    """
    Save MAIL lists from memory to the local filesystem.
    """

    logger.info(f"saving {len(lists)} lists...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("lists"),
        {
            address: mail_list.model_dump_json()
            for address, mail_list in lists.items()
        },
    )


async def save_message_buffer(message_buffer: list[str]) -> None:
    """
    Save message delivery queue from memory to the local filesystem.
    """

    logger.info(f"saving {len(message_buffer)} messages to buffer...")

    _atomic_write_text(
        DEPLOYMENT_PATH.joinpath("message_buffer.lock"),
        "".join(f"{msg_id}\n" for msg_id in message_buffer),
    )


async def save_webhooks(webhooks: dict[str, MAILWebhook]) -> None:
    """
    Save server webhooks from memory to the local filesystem.
    """

    logger.info(f"saving {len(webhooks)} webhooks...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("webhooks"),
        {
            webhook.webhook_id: webhook.model_dump_json()
            for webhook in webhooks.values()
        },
    )


async def save_refresh_tokens(
    refresh_tokens: dict[str, RefreshTokenRecord],
) -> None:
    """
    Save refresh tokens from memory to the local filesystem, one file per token
    keyed by its hash.
    """

    logger.info(f"saving {len(refresh_tokens)} refresh_tokens...")

    _save_directory_snapshot(
        DEPLOYMENT_PATH.joinpath("refresh_tokens"),
        {
            token_hash: record.model_dump_json()
            for token_hash, record in refresh_tokens.items()
        },
    )
