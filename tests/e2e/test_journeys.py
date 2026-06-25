# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Full-system journeys: real server + real daemon + real CLI over the
wire. These are the only tests that exercise env-var wiring,
backend-init provisioning, daemon polling, and shutdown persistence
in combination.
"""

import httpx

# Mirrors the cast provisioned by the e2e_stack fixture (conftest.py).
HOST = "localhost"
SWARM = "chorus"
ADMIN = f"admin:root@{HOST}"
USER = f"user:alice@{HOST}"
OTHER_USER = f"user:bob@{HOST}"
AGENT = f"sage@{SWARM}@{HOST}"
# Full address: used as a message recipient (delivery resolves the full
# ``list:`` form). The list HTTP/CLI surface addresses it by local form.
LIST_ADDRESS = f"list:town-square@{SWARM}@{HOST}"
LIST_LOCAL_ADDRESS = f"town-square@{SWARM}"


def test_send_deliver_read_journey(e2e_stack) -> None:
    alice = e2e_stack.login(USER)
    bob = e2e_stack.login(OTHER_USER)

    draft = e2e_stack.cli_json(
        "compose", "Assembly tonight", "The chorus convenes at dusk.", token=alice
    )
    draft_id = draft["entry"]["draft"]["draft_id"]

    sent = e2e_stack.cli_json("send", draft_id, OTHER_USER, token=alice)
    message_id = sent["message"]["message_id"]

    def bob_has_mail() -> bool:
        inbox = e2e_stack.cli_json("inbox", token=bob)
        return any(e["message_id"] == message_id for e in inbox["entries"])

    with e2e_stack.daemon_running():
        e2e_stack.wait_for(bob_has_mail)

    opened = e2e_stack.cli_json("inbox-open", message_id, token=bob)
    assert opened["entry"]["message"]["sender"] == USER
    assert opened["entry"]["message"]["body"] == "The chorus convenes at dusk."

    outbox = e2e_stack.cli_json("outbox-open", message_id, token=alice)
    assert outbox["entry"]["delivered_at"] is not None


def test_list_fan_out_journey(e2e_stack) -> None:
    admin = e2e_stack.login(ADMIN)
    alice = e2e_stack.login(USER)
    bob = e2e_stack.login(OTHER_USER)

    # List creation is admin-surface; drive it via the HTTP API with a
    # CLI-obtained admin token.
    response = httpx.post(
        f"{e2e_stack.base_url}/admin/lists",
        json={
            "name": "town-square",
            "swarm_name": SWARM,
            "owner": ADMIN,
            "members": [AGENT],
        },
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert response.status_code == 200, response.text

    # Bob subscribes himself through the CLI.
    subscribed = e2e_stack.cli_json("list-subscribe", LIST_LOCAL_ADDRESS, token=bob)
    assert OTHER_USER in subscribed["mail_list"]["members"]

    draft = e2e_stack.cli_json("compose", "To the square", "Hear ye.", token=alice)
    sent = e2e_stack.cli_json(
        "send", draft["entry"]["draft"]["draft_id"], LIST_ADDRESS, token=alice
    )
    message_id = sent["message"]["message_id"]

    def bob_has_mail() -> bool:
        inbox = e2e_stack.cli_json("inbox", token=bob)
        return any(e["message_id"] == message_id for e in inbox["entries"])

    with e2e_stack.daemon_running():
        e2e_stack.wait_for(bob_has_mail)

    # The agent member received the fan-out too.
    sage = e2e_stack.login(AGENT)
    opened = e2e_stack.cli_json("inbox-open", message_id, token=sage)
    assert opened["entry"]["message"]["subject"] == "To the square"


def test_persistence_across_restart(e2e_stack) -> None:
    alice = e2e_stack.login(USER)
    bob = e2e_stack.login(OTHER_USER)

    draft = e2e_stack.cli_json("compose", "Durable", "Survives restarts.", token=alice)
    sent = e2e_stack.cli_json(
        "send", draft["entry"]["draft"]["draft_id"], OTHER_USER, token=alice
    )
    message_id = sent["message"]["message_id"]

    def bob_has_mail() -> bool:
        inbox = e2e_stack.cli_json("inbox", token=bob)
        return any(e["message_id"] == message_id for e in inbox["entries"])

    with e2e_stack.daemon_running():
        e2e_stack.wait_for(bob_has_mail)

    e2e_stack.restart_server()

    # Tokens are stateless JWTs signed with the same secret, so they
    # remain valid; the inbox must survive the shutdown/startup cycle.
    opened = e2e_stack.cli_json("inbox-open", message_id, token=bob)
    assert opened["entry"]["message"]["body"] == "Survives restarts."
    outbox = e2e_stack.cli_json("outbox", token=alice)
    assert any(e["message_id"] == message_id for e in outbox["entries"])


def test_periodic_persistence_survives_abrupt_server_exit(e2e_stack) -> None:
    e2e_stack.stop_server()
    e2e_stack.start_server(memory_save_interval=0.2)

    alice = e2e_stack.login(USER)
    bob = e2e_stack.login(OTHER_USER)

    draft = e2e_stack.cli_json(
        "compose", "Checkpointed", "Survives abrupt exit.", token=alice
    )
    sent = e2e_stack.cli_json(
        "send", draft["entry"]["draft"]["draft_id"], OTHER_USER, token=alice
    )
    message_id = sent["message"]["message_id"]

    def bob_has_mail() -> bool:
        inbox = e2e_stack.cli_json("inbox", token=bob)
        return any(e["message_id"] == message_id for e in inbox["entries"])

    with e2e_stack.daemon_running():
        e2e_stack.wait_for(bob_has_mail)

    deployment = e2e_stack.home / ".mail-swarms" / "deployments" / "default"

    def checkpoint_written() -> bool:
        inbox_path = deployment / "inboxes" / OTHER_USER
        return (
            (deployment / "messages" / message_id).exists()
            and (deployment / "inbox_entries" / message_id).exists()
            and inbox_path.exists()
            and message_id in inbox_path.read_text(encoding="utf-8").splitlines()
        )

    e2e_stack.wait_for(checkpoint_written, timeout=10.0)

    e2e_stack.kill_server()
    e2e_stack.start_server(memory_save_interval=0)

    opened = e2e_stack.cli_json("inbox-open", message_id, token=bob)
    assert opened["entry"]["message"]["body"] == "Survives abrupt exit."
    outbox = e2e_stack.cli_json("outbox", token=alice)
    assert any(e["message_id"] == message_id for e in outbox["entries"])


def test_auth_journey(e2e_stack) -> None:
    # Ping needs no credentials.
    result = e2e_stack.cli("ping")
    assert result.returncode == 0

    # A bad password fails loudly.
    bad = e2e_stack.cli("login")  # no MAIL_ADDRESS/MAIL_PASSWORD in env
    assert bad.returncode != 0

    alice = e2e_stack.login(USER)
    whoami = e2e_stack.cli_json("whoami", token=alice)
    assert whoami["user_agent"]["user_agent"]["user_id"] == "alice"

    # The swarm directory requires the token.
    no_auth = e2e_stack.cli("swarm-list")
    assert no_auth.returncode != 0
    swarms = e2e_stack.cli_json("swarm-list", token=alice)
    assert [s["name"] for s in swarms["swarms"]] == [SWARM]
