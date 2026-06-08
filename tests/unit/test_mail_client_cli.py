# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import json
import uuid
from argparse import Namespace
from datetime import UTC, datetime

from mail_client.client import Newman
from mail_protocol.interswarm import MAILInterswarmMessage


def build_interswarm_message_dict() -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "interswarm_message_id": str(uuid.uuid4()),
        "source_swarm": "local-swarm",
        "target_swarm": "remote-swarm",
        "timestamp": now,
        "payload": {
            "id": str(uuid.uuid4()),
            "timestamp": now,
            "msg_type": "direct",
            "sender": {"addr_type": "agent", "address": "supervisor"},
            "recipients": [{"addr_type": "agent", "address": "weather@remote-swarm"}],
            "subject": "Delegated task",
            "body": "Fetch remote context",
            "task_id": str(uuid.uuid4()),
            "metadata": {},
        },
        "task": {
            "task_id": str(uuid.uuid4()),
            "task_owner": {
                "instance_type": "user",
                "instance_client_id": "user-123",
                "swarm_name": "local-swarm",
            },
            "task_contributors": [
                {
                    "instance_type": "swarm",
                    "instance_client_id": "remote-swarm",
                    "swarm_name": "local-swarm",
                }
            ],
            "start_time": now,
            "completed": False,
            "metadata": {},
        },
        "attachments": [],
        "metadata": {"trace_id": "trace-123"},
    }


def test_newman_interswarm_command_posts_validated_message(
    tmp_path,
) -> None:
    newman = Newman("http://example.com")
    newman._api_key = "swarm-token"
    newman._user_id = "local-swarm"
    newman._user_role = "swarm"

    captured: dict[str, object] = {}
    printed: list[object] = []

    class DummyResponse:
        status = "success"
        new_task = True

        def model_dump(self) -> dict[str, object]:
            return {
                "status": self.status,
                "new_task": self.new_task,
                "metadata": {},
            }

    class DummyClient:
        def post_interswarm_message(
            self,
            *,
            message: MAILInterswarmMessage,
            metadata: dict[str, object],
        ) -> DummyResponse:
            captured["message"] = message
            captured["metadata"] = metadata
            return DummyResponse()

    newman._client = DummyClient()
    newman._console.print = printed.append  # type: ignore[method-assignment]

    message_dict = build_interswarm_message_dict()
    message_path = tmp_path / "interswarm-message.json"
    message_path.write_text(json.dumps(message_dict))

    newman._cmd_interswarm(
        Namespace(
            message_json=None,
            file=str(message_path),
            metadata='{"request_id":"req-123"}',
            verbose=False,
        )
    )

    assert captured["message"] == MAILInterswarmMessage.model_validate(message_dict)
    assert captured["metadata"] == {"request_id": "req-123"}
    assert printed == ["interswarm message result: [green]success[/green] (new_task=True)"]
