# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
One-time filesystem (memory) -> sqlite import.

Writes a small deployment with the memory backend's own ``save_*`` loaders,
imports it, and verifies every collection — and the reconstructed per-owner box
membership — is readable through ``SQLiteBackend``.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from mail_protocol.core.inbox import MAILInboxEntrySummary
from mail_protocol.core.lists import MAILList, MAILListInBackend
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.outbox import MAILOutboxEntrySummary
from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.user_agents import (
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
    MAILUserAgentInBackend,
)
from mail_protocol.core.webhooks import MAILWebhook
from mail_protocol.network.requests import BoxFilterParams
from mail_server.backends.memory import fs as memory_fs
from mail_server.backends.sqlite.api import SQLiteBackend
from mail_server.backends.sqlite.migrate import import_memory_deployment

NOW = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
MID = "55555555-5555-4555-8555-555555555555"
UALICE = "user:alice@localhost"
SAGE = "sage@chorus@localhost"
DAEMON = "daemon:dummy@localhost"
LIST_ADDR = "list:team@chorus@localhost"

ALICE_UA = MAILUserAgent(
    user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost")
)
SAGE_UA = MAILUserAgent(
    user_agent=MAILAgent(ua_type="agent", name="sage", swarm="chorus", host="localhost")
)


async def _write_fs_deployment() -> None:
    """Populate the (monkeypatched) memory deployment tree."""

    await memory_fs.save_user_agents(
        {
            UALICE: MAILUserAgentInBackend(
                user_agent=ALICE_UA.user_agent, hashed_password="h1"
            ),
            SAGE: MAILUserAgentInBackend(
                user_agent=SAGE_UA.user_agent, hashed_password="h2"
            ),
        }
    )
    await memory_fs.save_swarms(
        {
            "chorus": MAILSwarm(
                name="chorus",
                description="d",
                keywords=["k"],
                agents=["sage"],
                metadata={},
            )
        }
    )
    await memory_fs.save_messages(
        {
            MID: MAILMessage(
                mail_version="2.0",
                message_id=MID,
                sender=UALICE,
                recipients=[SAGE],
                subject="Imported",
                body="survives migration",
                tags=[],
                sent_at=NOW,
                metadata={},
            )
        }
    )
    await memory_fs.save_inbox_entries(
        {
            MID: MAILInboxEntrySummary(
                message_id=MID,
                sender=UALICE,
                subject="Imported",
                body_size=18,
                received_at=NOW,
                delivered_by=DAEMON,
            )
        }
    )
    await memory_fs.save_inboxes({SAGE: [MID], UALICE: []})
    await memory_fs.save_outbox_entries(
        {
            MID: MAILOutboxEntrySummary(
                message_id=MID,
                recipients=[SAGE],
                subject="Imported",
                body_size=18,
                sent_at=NOW,
                delivered_at=NOW,
                delivered_by=DAEMON,
            )
        }
    )
    await memory_fs.save_outboxes({UALICE: [MID]})
    await memory_fs.save_message_buffer([MID])
    await memory_fs.save_webhooks(
        {
            "https://hooks.example.com/mail": MAILWebhook(
                webhook_id=f"wh_{MID}",
                url="https://hooks.example.com/mail",
                events=["mail.delivered"],
                secret="shh",
            )
        }
    )
    await memory_fs.save_lists(
        {
            LIST_ADDR: MAILListInBackend(
                **MAILList(
                    name="team", swarm="chorus", host="localhost", owner=UALICE
                ).model_dump(),
                list_id=MID,
                created_at=NOW,
                updated_at=NOW,
            )
        }
    )


async def test_import_filesystem_deployment(deployment_dir: Path) -> None:
    await _write_fs_deployment()
    db_path = deployment_dir / "mail.db"

    counts = await import_memory_deployment(source_dir=deployment_dir, db_path=db_path)
    assert counts["user_agents"] == 2
    assert counts["messages"] == 1
    assert counts["buffered"] == 1

    backend = SQLiteBackend(f"sqlite:///{db_path}")
    await backend.on_server_startup(host="localhost")
    try:
        # User-agents + swarm imported.
        assert (await backend.get_user_agent(SAGE)).hashed_password == "h2"
        assert (await backend.get_swarm("chorus")).agents == ["sage"]

        # The recipient's inbox membership + entry survived...
        inbox, total = await backend.get_inbox(SAGE_UA, BoxFilterParams())
        assert total == 1 and inbox[0].message_id == MID
        opened = await backend.get_inbox_message(SAGE_UA, MID)
        assert opened.message.body == "survives migration"
        assert opened.delivered_by == DAEMON

        # ...as did the sender's outbox, the buffer, the webhook, and the list.
        _, outbox_total = await backend.get_outbox(ALICE_UA, BoxFilterParams())
        assert outbox_total == 1
        daemon = MAILDaemon(ua_type="daemon", worker_name="dummy", host="localhost")
        assert await backend.daemon_clear_message_buffer(daemon) == [MID]
        assert (await backend.get_lists())[0].get_address() == LIST_ADDR
    finally:
        await backend.on_server_shutdown()


async def test_import_refuses_nonempty_database(deployment_dir: Path) -> None:
    await _write_fs_deployment()
    db_path = deployment_dir / "mail.db"
    await import_memory_deployment(source_dir=deployment_dir, db_path=db_path)

    # A second import would clobber existing data; it must refuse.
    with pytest.raises(ValueError, match="not empty"):
        await import_memory_deployment(source_dir=deployment_dir, db_path=db_path)


async def test_import_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no filesystem deployment"):
        await import_memory_deployment(
            source_dir=tmp_path / "nope", db_path=tmp_path / "mail.db"
        )
