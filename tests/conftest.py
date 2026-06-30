# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import os
from pathlib import Path

# mail_server.auth checks MAIL_JWT_SECRET_KEY and MAIL_JWT_ALGORITHM at
# import time. The values are inert for the in-process suites; set
# placeholders here (conftest loads before any test module) so
# mail_server.* imports succeed everywhere.
os.environ.setdefault("MAIL_JWT_SECRET_KEY", "test-secret-not-used")
os.environ.setdefault("MAIL_JWT_ALGORITHM", "HS256")
os.environ.setdefault("MAIL_REFRESH_TOKEN_EXPIRE_DAYS", "30")
# The TestClient speaks http://testserver; a ``Secure`` cookie would never be
# sent back over http, so disable the flag for the in-process suites. The
# secure-by-default behavior is covered by a dedicated unit test.
os.environ.setdefault("MAIL_COOKIE_SECURE", "false")

import pytest  # noqa: E402
from mail_server.backends.memory import fs as memory_fs  # noqa: E402
from mail_server.backends.memory.api import MemoryBackend  # noqa: E402

# Suite categories; see docs/testing-plan.md §3-4 for ownership boundaries.
CATEGORY_MARKERS = ("unit", "integration", "contract", "e2e")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Mark every test with the category of the ``tests/`` subdirectory it
    lives in, so ``-m`` selection (including the default ``-m "not e2e"``)
    works without per-file boilerplate.
    """
    for item in items:
        parts = item.path.parts
        for marker in CATEGORY_MARKERS:
            if marker in parts:
                item.add_marker(marker)


@pytest.fixture
def deployment_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """
    Redirect the memory backend's filesystem persistence into a tmp dir.

    The backend hard-codes ``~/.mail-swarms/deployments/default`` as the
    on-disk root; tests monkeypatch ``memory_fs.DEPLOYMENT_PATH`` so the
    write paths land somewhere isolated. Sub-dirs that the backend
    expects on startup are pre-created here for parity with how
    ``mail server`` provisions its own filesystem.
    """
    deployment = tmp_path / "deployment"
    for subdir in (
        "user_agents",
        "swarms",
        "messages",
        "inbox_entries",
        "inboxes",
        "read_inbox",
        "outbox_entries",
        "outboxes",
        "draft_entries",
        "drafts",
        "trash_entries",
        "trashes",
        "webhooks",
        "lists",
        "refresh_tokens",
    ):
        (deployment / subdir).mkdir(parents=True, exist_ok=True)
    (deployment / "message_buffer.lock").touch()

    monkeypatch.setattr(memory_fs, "DEPLOYMENT_PATH", deployment)
    return deployment


@pytest.fixture
async def backend(deployment_dir: Path) -> MemoryBackend:
    """
    A started ``MemoryBackend`` on ``localhost``, persisting into
    ``deployment_dir``. Test modules that need pre-seeded state should
    override this fixture locally.
    """
    instance = MemoryBackend()
    await instance.on_server_startup(host="localhost")
    return instance
