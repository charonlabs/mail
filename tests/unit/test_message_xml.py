import datetime

from mail.core.message import (
    MAILMessage,
    MAILRequest,
    build_body_xml,
    build_mail_xml,
    create_agent_address,
    create_user_address,
)


def test_build_body_xml_wraps_body_tag():
    xml = build_body_xml({"foo": "bar"})
    assert xml.startswith("<body>") and xml.endswith("</body>")
    assert "<foo>bar</foo>" in xml


def test_build_mail_xml_single_recipient_contains_basic_fields():
    msg: MAILMessage = MAILMessage(
        id="m1",
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        message=MAILRequest(
            task_id="t1",
            request_id="r1",
            sender=create_user_address("user-123"),
            recipient=create_agent_address("supervisor"),
            subject="S",
            body="B",
            sender_swarm=None,
            recipient_swarm=None,
            routing_info=None,
        ),
        msg_type="request",
    )
    rendered = build_mail_xml(msg)
    assert rendered["role"] == "user"
    content = rendered["content"]
    assert '<from type="user">user-123</from>' in content
    assert "<subject>S</subject>" in content and "<body>B</body>" in content


def test_build_mail_xml_multiple_recipients_contains_addresses():
    msg: MAILMessage = MAILMessage(
        id="m2",
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        message={
            "task_id": "t2",
            "request_id": "r2",
            "sender": create_user_address("user-456"),
            "recipients": [
                create_agent_address("analyst"),
                create_agent_address("helper"),
            ],
            "subject": "S2",
            "body": "B2",
            "sender_swarm": None,
            "recipient_swarms": None,
            "routing_info": None,
        },
        msg_type="broadcast",
    )
    rendered = build_mail_xml(msg)
    content = rendered["content"]
    # At minimum the address elements should appear
    assert '<address type="agent">analyst</address>' in content
    assert '<address type="agent">helper</address>' in content
