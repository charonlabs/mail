# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import os
from datetime import UTC, datetime
from pathlib import Path

# mail_server.auth checks these env vars at import time; these tests do not
# exercise JWT behavior.
os.environ.setdefault("MAIL_JWT_SECRET_KEY", "test-secret-not-used")
os.environ.setdefault("MAIL_JWT_ALGORITHM", "HS256")

import pytest
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILUser, MAILUserAgent
from mail_server.backends.memory import fs as memory_fs  # noqa: E402
from mail_server.backends.memory.api import MemoryBackend  # noqa: E402


@pytest.fixture
def deployment_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    deployment = tmp_path / "deployment"
    for subdir in (
        "user_agents",
        "swarms",
        "messages",
        "inbox_entries",
        "inboxes",
        "outbox_entries",
        "outboxes",
        "draft_entries",
        "drafts",
        "trash_entries",
        "trashes",
        "webhooks",
        "lists",
    ):
        (deployment / subdir).mkdir(parents=True, exist_ok=True)
    (deployment / "message_buffer.lock").touch()
    monkeypatch.setattr(memory_fs, "DEPLOYMENT_PATH", deployment)
    return deployment


@pytest.fixture
async def backend(deployment_dir: Path) -> MemoryBackend:
    instance = MemoryBackend()
    await instance.on_server_startup(host="localhost")
    return instance


def _make_user_agent() -> MAILUserAgent:
    return MAILUserAgent(
        user_agent=MAILUser(
            ua_type="user",
            user_id="ryan",
            host="localhost",
        )
    )


def _make_message() -> MAILMessage:
    return MAILMessage(
        message_id="11111111-1111-4111-8111-111111111111",
        sender="philosopher@chorus@localhost",
        recipients=["user:ryan@localhost"],
        subject="Trash lookup",
        body="This message should be read from trash, not drafts.",
        sent_at=datetime(2026, 6, 10, tzinfo=UTC),
        metadata={},
    )


@pytest.mark.asyncio
async def test_get_trash_message_reads_user_trash_box(
    backend: MemoryBackend,
) -> None:
    user_agent = _make_user_agent()
    message = _make_message()
    entry = MAILTrashEntry(
        message=message,
        trashed_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
    )

    user_address = user_agent.get_address()
    backend.trash_entries[message.message_id] = entry
    backend.trashes[user_address] = [message.message_id]
    backend.drafts[user_address] = []

    result = await backend.get_trash_message(
        user_agent=user_agent,
        message_id=message.message_id,
    )

    assert result == entry
