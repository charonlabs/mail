# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Server-side behavior for MAIL 2.0 reply/tag support: drafts carry reply_to
and tags through to the sent MAILMessage, and send-time tags merge with draft
tags as an order-preserving union.
"""

import pytest
from mail_protocol.core.user_agents import MAILUser, MAILUserAgent
from mail_protocol.network.requests import DraftPostRequest, DraftSendPostRequest
from mail_server.backends.memory.api import MemoryBackend

ORIGINAL_ID = "66666666-6666-4666-8666-666666666666"


def _make_user_agent() -> MAILUserAgent:
    return MAILUserAgent(
        user_agent=MAILUser(ua_type="user", user_id="alice", host="localhost")
    )


async def _seed_draft(
    backend: MemoryBackend, user_agent: MAILUserAgent, payload: DraftPostRequest
) -> str:
    address = user_agent.get_address()
    backend.drafts[address] = []
    backend.outboxes[address] = []
    draft_entry = await backend.post_draft(user_agent, payload)
    return draft_entry.draft.draft_id


@pytest.mark.asyncio
async def test_send_draft_propagates_mail_version_and_reply_to(
    backend: MemoryBackend,
) -> None:
    user_agent = _make_user_agent()
    draft_id = await _seed_draft(
        backend,
        user_agent,
        DraftPostRequest(
            subject="Re: Hi", body="A reply.", reply_to=ORIGINAL_ID, tags=[]
        ),
    )

    message = await backend.send_draft(
        user_agent,
        draft_id,
        DraftSendPostRequest(recipients=["philosopher@chorus@localhost"]),
    )

    assert message.mail_version == "2.0"
    assert message.reply_to == ORIGINAL_ID


@pytest.mark.asyncio
async def test_send_draft_merges_draft_and_send_tags(backend: MemoryBackend) -> None:
    user_agent = _make_user_agent()
    draft_id = await _seed_draft(
        backend,
        user_agent,
        DraftPostRequest(subject="Tagged", body="Body.", tags=["alpha", "beta"]),
    )

    message = await backend.send_draft(
        user_agent,
        draft_id,
        DraftSendPostRequest(
            recipients=["philosopher@chorus@localhost"], tags=["beta", "gamma"]
        ),
    )

    # Order-preserving union: draft tags first, then new send-time tags.
    assert message.tags == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_send_draft_without_reply_or_tags_is_unmarked(
    backend: MemoryBackend,
) -> None:
    user_agent = _make_user_agent()
    draft_id = await _seed_draft(
        backend,
        user_agent,
        DraftPostRequest(subject="Plain", body="Body."),
    )

    message = await backend.send_draft(
        user_agent,
        draft_id,
        DraftSendPostRequest(recipients=["philosopher@chorus@localhost"]),
    )

    assert message.reply_to is None
    assert message.tags == []
