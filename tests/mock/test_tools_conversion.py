from mail.factories.base import AgentToolCall
from mail.tools import convert_call_to_mail_message


def _call(name: str, args: dict) -> AgentToolCall:
    return AgentToolCall(
        tool_name=name,
        tool_args=args,
        tool_call_id="t1",
        completion={"role": "assistant", "content": "ok"},
    )


def test_convert_send_request():
    msg = convert_call_to_mail_message(
        _call("send_request", {"target": "analyst", "subject": "S", "message": "M"}),
        sender="supervisor",
        task_id="task-1",
    )
    assert msg["msg_type"] == "request"
    assert msg["message"]["recipient"]["address"] == "analyst"


def test_convert_send_response():
    msg = convert_call_to_mail_message(
        _call("send_response", {"target": "analyst", "subject": "S", "message": "M"}),
        sender="supervisor",
        task_id="task-1",
    )
    assert msg["msg_type"] == "response"
    assert msg["message"]["recipient"]["address"] == "analyst"


def test_convert_send_interrupt():
    msg = convert_call_to_mail_message(
        _call("send_interrupt", {"target": "analyst", "subject": "S", "message": "M"}),
        sender="supervisor",
        task_id="task-1",
    )
    assert msg["msg_type"] == "interrupt"
    assert msg["message"]["recipients"][0]["address"] == "analyst"


def test_convert_send_broadcast():
    msg = convert_call_to_mail_message(
        _call("send_broadcast", {"subject": "S", "message": "M"}),
        sender="supervisor",
        task_id="task-1",
    )
    assert msg["msg_type"] == "broadcast"
    assert msg["message"]["recipients"][0]["address"] == "all"


def test_convert_task_complete():
    msg = convert_call_to_mail_message(
        _call("task_complete", {"finish_message": "done"}),
        sender="supervisor",
        task_id="task-1",
    )
    assert msg["msg_type"] == "broadcast_complete"
    assert msg["message"]["body"] == "done"
