# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import UTC, datetime

import pytest
from mail_protocol.core.messages import MAILMessage
from mail_protocol.core.trash import MAILTrashEntry
from mail_protocol.core.user_agents import MAILUser, MAILUserAgent
from mail_server.backends.memory.api import MemoryBackend


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
        mail_version="2.0",
        message_id="11111111-1111-4111-8111-111111111111",
        sender="philosopher@chorus@localhost",
        recipients=["user:ryan@localhost"],
        subject="Trash lookup",
        body="This message should be read from trash, not drafts.",
        tags=[],
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
