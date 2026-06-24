# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
The durability property the sqlite backend exists to provide: a committed
message survives an abrupt ``kill -9`` with no graceful shutdown — the window
the memory backend's checkpoint cannot close.
"""

HOST = "localhost"
USER = f"user:alice@{HOST}"
OTHER_USER = f"user:bob@{HOST}"


def test_sqlite_committed_message_survives_sigkill(sqlite_e2e_stack) -> None:
    stack = sqlite_e2e_stack
    alice = stack.login(USER)
    bob = stack.login(OTHER_USER)

    draft = stack.cli_json(
        "compose", "Durable", "Survives kill -9.", token=alice
    )
    sent = stack.cli_json(
        "send", draft["entry"]["draft"]["draft_id"], OTHER_USER, token=alice
    )
    message_id = sent["message"]["message_id"]

    def bob_has_mail() -> bool:
        inbox = stack.cli_json("inbox", token=bob)
        return any(e["message_id"] == message_id for e in inbox["entries"])

    with stack.daemon_running():
        stack.wait_for(bob_has_mail)

    # SIGKILL: no lifespan shutdown, no checkpoint — only what is already
    # committed to the sqlite file can survive.
    stack.kill_server()
    stack.start_server()

    # JWTs are stateless, so the tokens remain valid across the restart.
    opened = stack.cli_json("inbox-open", message_id, token=bob)
    assert opened["entry"]["message"]["body"] == "Survives kill -9."
    outbox = stack.cli_json("outbox", token=alice)
    assert any(e["message_id"] == message_id for e in outbox["entries"])
