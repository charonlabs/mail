import asyncio

import pytest

from mail.core import MAILRuntime
from mail.core.message import (
    MAILMessage,
    MAILRequest,
    create_agent_address,
    create_user_address,
)


@pytest.mark.asyncio
async def test_submit_and_wait_resolves_on_task_complete():
    async def stub_agent(history, tool_choice):  # noqa: ARG001
        from mail.factories.base import AgentToolCall

        call = AgentToolCall(
            tool_name="task_complete",
            tool_args={"finish_message": "All good"},
            tool_call_id="c1",
            completion={"role": "assistant", "content": "ok"},
        )
        return None, [call]

    mail = MAILRuntime(
        agents={"supervisor": stub_agent},
        actions={},
        user_id="user-1",
        swarm_name="example",
        swarm_registry=None,
        enable_interswarm=False,
    )

    msg: MAILMessage = MAILMessage(
        id="m1",
        timestamp="2024-01-01T00:00:00Z",
        message=MAILRequest(
            task_id="t1",
            request_id="r1",
            sender=create_user_address("user-1"),
            recipient=create_agent_address("supervisor"),
            subject="Hello",
            body="Do the thing",
        ),
        msg_type="request",
    )

    # Start continuous processing to consume the queue
    loop_task = asyncio.create_task(mail.run_continuous())
    try:
        # Give the loop a tick to start
        await asyncio.sleep(0)

        # Submit and wait should resolve quickly from stub agent
        result = await asyncio.wait_for(
            mail.submit_and_wait(msg, timeout=2.0), timeout=3.0
        )
    finally:
        await mail.shutdown()
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
    assert result["msg_type"] == "broadcast_complete"
    assert result["message"]["body"] == "All good"
