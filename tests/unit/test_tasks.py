# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import uuid

import ujson
from sse_starlette import ServerSentEvent

from mail.core.message import MAILMessage, MAILRequest, create_agent_address
from mail.core.tasks import MAILTask


def test_get_messages_parses_json_event_data() -> None:
    task = MAILTask(task_id="task-1", task_owner="user:1@swarm", task_contributors=[])
    message = MAILMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        message=MAILRequest(
            task_id="task-1",
            request_id=str(uuid.uuid4()),
            sender=create_agent_address("sender"),
            recipient=create_agent_address("recipient"),
            subject="Hello",
            body="Body",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info={},
        ),
        msg_type="request",
    )
    payload = {
        "description": "new message",
        "task_id": "task-1",
        "extra_data": {"full_message": message},
    }
    task.add_event(
        ServerSentEvent(event="new_message", data=ujson.dumps(payload))
    )

    messages = task.get_messages()
    assert messages == [message]
