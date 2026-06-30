# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline


import secrets
from pathlib import Path

from mail_protocol.core.swarms import MAILSwarm
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgentInBackend,
)
from pwdlib import PasswordHash


def init_memory_backend(
    deployment: str = "default",
    swarm: str = "default",
    swarm_description: str = "A MAIL swarm",
    swarm_keywords: list[str] = [],
    agents: list[str] = ["supervisor"],
    daemons: list[str] = ["dummy"],
    users: list[str] = ["dummy"],
    admins: list[str] = ["dummy"],
    host: str = "example.com",
) -> None:
    """
    Initialize a fresh memory backend for `mail-server`.
    """

    # ensure required local directories exist
    # ~/.mail-swarms
    MAIL_PATH = Path.home().joinpath(".mail-swarms")
    # print(f"ensuring local .mail-swarms directory: {MAIL_PATH}...")
    MAIL_PATH.mkdir(exist_ok=True)
    print(f"ensured local .mail-swarms directory: {MAIL_PATH}")

    # ~/.mail-swarms/deployments
    DEPLOYMENTS_PATH = MAIL_PATH.joinpath("deployments")
    # print(f"ensuring local deployments path: {DEPLOYMENTS_PATH}...")
    DEPLOYMENTS_PATH.mkdir(exist_ok=True)
    print(f"ensured local deployments path: {DEPLOYMENTS_PATH}")

    # ~/.mail-swarms/deployments/{deployment}
    DEPLOYMENT_PATH = DEPLOYMENTS_PATH.joinpath(deployment)
    # print(f"ensuring local deployment path: {DEPLOYMENT_PATH}")
    DEPLOYMENT_PATH.mkdir(exist_ok=True)
    print(f"ensured local deployment path: {DEPLOYMENT_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/swarms
    SWARMS_PATH = DEPLOYMENT_PATH.joinpath("swarms")
    SWARMS_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment swarms path: {SWARMS_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/user_agents
    USER_AGENTS_PATH = DEPLOYMENT_PATH.joinpath("user_agents")
    USER_AGENTS_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment user_agents path: {USER_AGENTS_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/messages
    MESSAGES_PATH = DEPLOYMENT_PATH.joinpath("messages")
    MESSAGES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment messages path: {MESSAGES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/message_buffer.lock
    MESSAGE_BUFFER_PATH = DEPLOYMENT_PATH.joinpath("message_buffer.lock")
    MESSAGE_BUFFER_PATH.touch()
    print(f"ensured deployment message buffer path: {MESSAGE_BUFFER_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/inbox_entries
    INBOX_ENTRIES_PATH = DEPLOYMENT_PATH.joinpath("inbox_entries")
    # print(f"ensuring deployment inbox entries path: {INBOX_ENTRIES_PATH}")
    INBOX_ENTRIES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment inbox entries path: {INBOX_ENTRIES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/inboxes
    INBOXES_PATH = DEPLOYMENT_PATH.joinpath("inboxes")
    # print(f"ensuring deployment inboxes: {INBOXES_PATH}")
    INBOXES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment inboxes: {INBOXES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/read_inbox
    READ_INBOX_PATH = DEPLOYMENT_PATH.joinpath("read_inbox")
    READ_INBOX_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment read_inbox: {READ_INBOX_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/outbox_entries
    OUTBOX_ENTRIES_PATH = DEPLOYMENT_PATH.joinpath("outbox_entries")
    # print(f"ensuring deployment outbox_entries: {OUTBOX_ENTRIES_PATH}")
    OUTBOX_ENTRIES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment outbox_entries: {OUTBOX_ENTRIES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/outboxes
    OUTBOXES_PATH = DEPLOYMENT_PATH.joinpath("outboxes")
    # print(f"ensuring deployment outboxes: {OUTBOXES_PATH}")
    OUTBOXES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment outboxes: {OUTBOXES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/draft_entries
    DRAFT_ENTRIES_PATH = DEPLOYMENT_PATH.joinpath("draft_entries")
    # print(f"ensuring deployment draft_entries path: {DRAFT_ENTRIES_PATH}")
    DRAFT_ENTRIES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment draft_entries path: {DRAFT_ENTRIES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/drafts
    DRAFTS_PATH = DEPLOYMENT_PATH.joinpath("drafts")
    # print(f"ensuring deployment drafts path: {DRAFTS_PATH}")
    DRAFTS_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment drafts path: {DRAFTS_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/trash_entries
    TRASH_ENTRIES_PATH = DEPLOYMENT_PATH.joinpath("trash_entries")
    # print(f"ensuring deployment trash_entries: {TRASH_ENTRIES_PATH}")
    TRASH_ENTRIES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment trash_entries: {TRASH_ENTRIES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/trashes
    TRASHES_PATH = DEPLOYMENT_PATH.joinpath("trashes")
    # print(f"ensuring deployment trashes: {TRASHES_PATH}")
    TRASHES_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment trashes: {TRASHES_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/webhooks
    WEBHOOKS_PATH = DEPLOYMENT_PATH.joinpath("webhooks")
    WEBHOOKS_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment webhooks: {WEBHOOKS_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/lists
    LISTS_PATH = DEPLOYMENT_PATH.joinpath("lists")
    LISTS_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment lists: {LISTS_PATH}")

    # ~/.mail-swarms/deployments/{deployment}/refresh_tokens
    REFRESH_TOKENS_PATH = DEPLOYMENT_PATH.joinpath("refresh_tokens")
    REFRESH_TOKENS_PATH.mkdir(exist_ok=True)
    print(f"ensured deployment refresh_tokens: {REFRESH_TOKENS_PATH}")

    # write swarm file
    SWARM_PATH = SWARMS_PATH.joinpath(swarm)
    with open(SWARM_PATH, "w") as swarm_file:
        content = MAILSwarm(
            name=swarm,
            description=swarm_description,
            keywords=swarm_keywords,
            agents=agents,
            metadata={},
        ).model_dump_json()
        swarm_file.write(content)
    print(f"wrote swarm file: {SWARM_PATH}")

    hash = PasswordHash.recommended()
    SECRETS_PATH = DEPLOYMENT_PATH.joinpath(".secrets")
    SECRETS_PATH.mkdir(exist_ok=True)

    # write agent(s)
    for agent_name in agents:
        agent = MAILAgent(
            ua_type="agent",
            name=agent_name,
            swarm=swarm,
            host=host,
        )
        address = agent.get_address()
        password = secrets.token_urlsafe(32)
        hashed_password = hash.hash(password)
        ua_in_backend = MAILUserAgentInBackend(
            user_agent=agent,
            hashed_password=hashed_password,
        )

        # write user_agent file
        AGENT_PATH = USER_AGENTS_PATH.joinpath(address)
        with open(AGENT_PATH, "w") as ua_file:
            content = ua_in_backend.model_dump_json()
            ua_file.write(content)

        # touch inbox file
        AGENT_INBOX = INBOXES_PATH.joinpath(address)
        AGENT_INBOX.touch()
        # touch outbox file
        AGENT_OUTBOX = OUTBOXES_PATH.joinpath(address)
        AGENT_OUTBOX.touch()
        # touch drafts file
        AGENT_DRAFTS = DRAFTS_PATH.joinpath(address)
        AGENT_DRAFTS.touch()
        # touch trash file
        AGENT_TRASH = TRASHES_PATH.joinpath(address)
        AGENT_TRASH.touch()

        print(f"wrote new agent: {address}")

        # write user_agent secret file
        AGENT_SECRET_PATH = SECRETS_PATH.joinpath(address)
        with open(AGENT_SECRET_PATH, "w") as pwd_file:
            content = password
            pwd_file.write(content)
        print(f"wrote agent password: {AGENT_SECRET_PATH}")

    # write daemon(s)
    for daemon_name in daemons:
        daemon = MAILDaemon(
            ua_type="daemon",
            worker_name=daemon_name,
            host=host,
        )
        address = daemon.get_address()
        password = secrets.token_urlsafe(32)
        hashed_password = hash.hash(password)
        ua_in_backend = MAILUserAgentInBackend(
            user_agent=daemon,
            hashed_password=hashed_password,
        )

        # write user_agent file
        DAEMON_PATH = USER_AGENTS_PATH.joinpath(address)
        with open(DAEMON_PATH, "w") as ua_file:
            content = ua_in_backend.model_dump_json()
            ua_file.write(content)

        # touch inbox file
        DAEMON_INBOX = INBOXES_PATH.joinpath(address)
        DAEMON_INBOX.touch()
        # touch outbox file
        DAEMON_OUTBOX = OUTBOXES_PATH.joinpath(address)
        DAEMON_OUTBOX.touch()
        # touch drafts file
        DAEMON_DRAFTS = DRAFTS_PATH.joinpath(address)
        DAEMON_DRAFTS.touch()
        # touch trash file
        DAEMON_TRASH = TRASHES_PATH.joinpath(address)
        DAEMON_TRASH.touch()

        print(f"wrote new daemon: {address}")

        # write user_agent secret file
        DAEMON_SECRET_PATH = SECRETS_PATH.joinpath(address)
        with open(DAEMON_SECRET_PATH, "w") as pwd_file:
            content = password
            pwd_file.write(content)
        print(f"wrote daemon password: {DAEMON_SECRET_PATH}")

    # write user(s)
    for user_name in users:
        user = MAILUser(
            ua_type="user",
            user_id=user_name,
            host=host,
        )
        address = user.get_address()
        password = secrets.token_urlsafe(32)
        hashed_password = hash.hash(password)
        ua_in_backend = MAILUserAgentInBackend(
            user_agent=user,
            hashed_password=hashed_password,
        )

        # write user_agent file
        USER_PATH = USER_AGENTS_PATH.joinpath(address)
        with open(USER_PATH, "w") as ua_file:
            content = ua_in_backend.model_dump_json()
            ua_file.write(content)

        # touch inbox file
        USER_INBOX = INBOXES_PATH.joinpath(address)
        USER_INBOX.touch()
        # touch outbox file
        USER_OUTBOX = OUTBOXES_PATH.joinpath(address)
        USER_OUTBOX.touch()
        # touch drafts file
        USER_DRAFTS = DRAFTS_PATH.joinpath(address)
        USER_DRAFTS.touch()
        # touch trash file
        USER_TRASH = TRASHES_PATH.joinpath(address)
        USER_TRASH.touch()

        print(f"wrote new user: {address}")

        # write user_agent secret file
        USER_SECRET_PATH = SECRETS_PATH.joinpath(address)
        with open(USER_SECRET_PATH, "w") as pwd_file:
            content = password
            pwd_file.write(content)
        print(f"wrote user password: {USER_SECRET_PATH}")

    # write admin(s)
    for admin_name in admins:
        admin = MAILAdmin(
            ua_type="admin",
            admin_id=admin_name,
            host=host,
        )
        address = admin.get_address()
        password = secrets.token_urlsafe(32)
        hashed_password = hash.hash(password)
        ua_in_backend = MAILUserAgentInBackend(
            user_agent=admin,
            hashed_password=hashed_password,
        )

        # write user_agent file
        ADMIN_PATH = USER_AGENTS_PATH.joinpath(address)
        with open(ADMIN_PATH, "w") as ua_file:
            content = ua_in_backend.model_dump_json()
            ua_file.write(content)

        # touch inbox file
        ADMIN_INBOX = INBOXES_PATH.joinpath(address)
        ADMIN_INBOX.touch()
        # touch outbox file
        ADMIN_OUTBOX = OUTBOXES_PATH.joinpath(address)
        ADMIN_OUTBOX.touch()
        # touch drafts file
        ADMIN_DRAFTS = DRAFTS_PATH.joinpath(address)
        ADMIN_DRAFTS.touch()
        # touch trash file
        ADMIN_TRASH = TRASHES_PATH.joinpath(address)
        ADMIN_TRASH.touch()

        print(f"wrote new admin: {address}")

        # write user_agent secret file
        ADMIN_SECRET_PATH = SECRETS_PATH.joinpath(address)
        with open(ADMIN_SECRET_PATH, "w") as pwd_file:
            content = password
            pwd_file.write(content)
        print(f"wrote admin password: {ADMIN_SECRET_PATH}")
