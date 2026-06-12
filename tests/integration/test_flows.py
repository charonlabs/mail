# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Cross-endpoint journeys driven entirely through the public API:
compose → send → buffer-clear → deliver → read.
"""

from fastapi.testclient import TestClient

ADMIN = "admin:ryan@localhost"
USER = "user:alice@localhost"
OTHER_USER = "user:bob@localhost"
AGENT = "sage@chorus@localhost"
LIST_ADDRESS = "list:welfare-discourse@chorus@localhost"


def test_send_and_read_journey(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(
        USER,
        [OTHER_USER, AGENT],
        subject="Assembly tonight",
        body="The chorus convenes at dusk.",
    )

    # Both recipients can open the message from their inbox.
    for recipient in (OTHER_USER, AGENT):
        response = app_client.get(
            f"/inbox/{message_id}", headers=headers_for(recipient)
        )
        assert response.status_code == 200
        message = response.json()["entry"]["message"]
        assert message["sender"] == USER
        assert message["subject"] == "Assembly tonight"
        assert message["body"] == "The chorus convenes at dusk."

    # The sender's outbox reflects the delivery.
    response = app_client.get(f"/outbox/{message_id}", headers=headers_for(USER))
    assert response.status_code == 200
    assert sorted(response.json()["entry"]["message"]["recipients"]) == sorted(
        [OTHER_USER, AGENT]
    )


def test_list_fan_out_journey(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    admin_headers = headers_for(ADMIN)

    # Admin creates a list with the agent as an initial member.
    response = app_client.post(
        "/admin/lists",
        json={
            "name": "welfare-discourse",
            "swarm_name": "chorus",
            "owner": ADMIN,
            "members": [AGENT],
        },
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    # Bob subscribes himself through the public endpoint.
    response = app_client.post(
        f"/lists/{LIST_ADDRESS}/subscribe", headers=headers_for(OTHER_USER)
    )
    assert response.status_code == 200
    assert OTHER_USER in response.json()["mail_list"]["members"]

    # Alice sends to the list address; the daemon fans out to members.
    message_id = deliver_message(USER, [LIST_ADDRESS], subject="To the list")

    for member in (AGENT, OTHER_USER):
        response = app_client.get(
            f"/inbox/{message_id}", headers=headers_for(member)
        )
        assert response.status_code == 200
        assert response.json()["entry"]["message"]["subject"] == "To the list"

    # The sender is not a member and receives nothing.
    response = app_client.get("/inbox/", headers=headers_for(USER))
    assert response.json()["entries"] == []
