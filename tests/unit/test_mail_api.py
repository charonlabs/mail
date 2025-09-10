import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest


class FakeMAIL:
    """Lightweight stub for mail.core.MAIL used by MAILSwarm tests."""

    def __init__(
        self,
        agents: Any,
        actions: Any,
        user_id: str,
        swarm_name: str,
        entrypoint: str,
    ) -> None:
        self.agents = agents
        self.actions = actions
        self.user_id = user_id
        self.swarm_name = swarm_name
        self.entrypoint = entrypoint
        self.submitted: list[dict[str, Any]] = []
        self._events: dict[str, list[Any]] = {}

    @pytest.mark.asyncio
    async def submit_and_wait(
        self, message: dict[str, Any], _timeout: float = 3600.0
    ) -> dict[str, Any]:
        self.submitted.append(message)
        task_id = message["message"]["task_id"]
        self._events.setdefault(task_id, []).append({"event": "debug", "data": "ok"})
        # Minimal response echoing back task_id and flipping sender/recipient
        return {
            "id": "resp-1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "message": {
                "task_id": task_id,
                "request_id": message["message"]["request_id"],
                "sender": message["message"]["recipient"],
                "recipient": message["message"]["sender"],
                "subject": "ok",
                "body": "done",
                "sender_swarm": self.swarm_name,
                "recipient_swarm": self.swarm_name,
                "routing_info": {},
            },
            "msg_type": "response",
        }

    def get_events_by_task_id(self, task_id: str) -> list[Any]:
        return self._events.get(task_id, [])

    @pytest.mark.asyncio
    async def submit_and_stream(
        self, _message: dict[str, Any], _timeout: float = 3600.0
    ) -> AsyncGenerator[dict[str, Any], None]:
        async def _stream() -> AsyncGenerator[dict[str, Any], None]:
            yield {"event": "message", "data": "chunk1"}
            yield {"event": "message", "data": "chunk2"}

        return _stream()


@pytest.fixture(autouse=True)
def patch_mail_in_api(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the MAIL symbol used inside mail.api to avoid heavy runtime behavior
    import mail.api as api

    monkeypatch.setattr(api, "MAIL", FakeMAIL)


def test_from_swarm_json_valid_creates_swarm() -> None:
    from mail.api import MAILSwarm

    data = {
        "name": "myswarm",
        "agents": [],
        "actions": [],
        "entrypoint": "supervisor",
        "user_id": "u-1",
    }

    swarm = MAILSwarm.from_swarm_json(json.dumps(data))
    assert swarm.swarm_name == "myswarm"
    assert swarm.entrypoint == "supervisor"
    # Ensure runtime was created with our stub
    assert isinstance(swarm._runtime, FakeMAIL)
    assert swarm._runtime.user_id == "u-1"
    assert swarm._runtime.swarm_name == "myswarm"


@pytest.mark.parametrize(
    "missing",
    ["name", "agents", "actions", "entrypoint"],
)
def test_from_swarm_json_missing_required_field_raises(missing: str) -> None:
    from mail.api import MAILSwarm

    base = {
        "name": "x",
        "agents": [],
        "actions": [],
        "entrypoint": "supervisor",
    }
    bad = base.copy()
    bad.pop(missing)

    with pytest.raises(ValueError) as exc:
        MAILSwarm.from_swarm_json(json.dumps(bad))
    assert "missing required field" in str(exc.value)


def test_from_swarm_json_wrong_types_raise() -> None:
    from mail.api import MAILSwarm

    bad = {
        "name": 123,
        "agents": {},
        "actions": {},
        "entrypoint": 999,
    }

    with pytest.raises(ValueError) as exc:
        MAILSwarm.from_swarm_json(json.dumps(bad))
    # Message should note type mismatch
    assert "must be of type" in str(exc.value)


def test_from_swarm_json_file_selects_named_swarm(tmp_path: Any) -> None:
    from mail.api import MAILSwarm

    contents = [
        {"name": "other", "agents": [], "actions": [], "entrypoint": "s"},
        {"name": "target", "agents": [], "actions": [], "entrypoint": "s"},
    ]
    path = tmp_path / "swarms.json"
    path.write_text(json.dumps(contents))

    swarm = MAILSwarm.from_swarm_json_file(str(path), "target")
    assert swarm.swarm_name == "target"


@pytest.mark.asyncio
async def test_post_message_uses_default_entrypoint_and_returns_events() -> None:
    from mail.api import MAILSwarm

    swarm = MAILSwarm(
        swarm_name="myswarm",
        agents=[],
        actions=[],
        entrypoint="supervisor",
    )

    # Call without explicit entrypoint -> defaults to MAILSwarm.entrypoint
    resp, events = await swarm.post_message(
        subject="hello", body="world", show_events=True
    )

    assert resp["msg_type"] == "response"
    # Ensure the request was submitted targeting the default entrypoint
    submitted = swarm._runtime.submitted  # type: ignore[attr-defined]
    assert len(submitted) == 1
    target = submitted[0]["message"]["recipient"]
    assert isinstance(target, dict) and target.get("address") == "supervisor"
    assert isinstance(events, list) and len(events) >= 1


@pytest.mark.asyncio
async def test_post_message_stream_headers_and_type() -> None:
    from sse_starlette import EventSourceResponse
    from mail.api import MAILSwarm

    swarm = MAILSwarm(
        swarm_name="myswarm",
        agents=[],
        actions=[],
        entrypoint="supervisor",
    )

    stream_resp = await swarm.post_message_stream(subject="hello", body="world")
    assert isinstance(stream_resp, EventSourceResponse)
    for key in ("Cache-Control", "Connection", "X-Accel-Buffering"):
        assert key in stream_resp.headers


def test_build_message_request_validation() -> None:
    from mail.api import MAILSwarm

    swarm = MAILSwarm(
        swarm_name="myswarm",
        agents=[],
        actions=[],
        entrypoint="supervisor",
    )

    # _build_message should require exactly one target for requests
    with pytest.raises(ValueError):
        swarm._build_message("subj", "body", ["a", "b"], type="request")
