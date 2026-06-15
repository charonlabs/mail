# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from mail_server.backends.memory.api import MemoryBackend

UUID = "55555555-5555-4555-8555-555555555555"


async def _wait_for(condition: Callable[[], bool], timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def test_negative_checkpoint_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        MemoryBackend(persistence_interval_seconds=-1)


async def test_zero_checkpoint_interval_disables_periodic_task(
    deployment_dir: Path,
) -> None:
    backend = MemoryBackend(persistence_interval_seconds=0)
    await backend.on_server_startup(host="localhost")

    try:
        assert backend._checkpoint_task is None
    finally:
        await backend.on_server_shutdown()


async def test_periodic_checkpoint_persists_without_shutdown(
    deployment_dir: Path,
) -> None:
    backend = MemoryBackend(persistence_interval_seconds=0.05)
    await backend.on_server_startup(host="localhost")

    target = deployment_dir / "message_buffer.lock"
    try:
        backend.message_buffer.append(UUID)

        await _wait_for(
            lambda: target.read_text(encoding="utf-8").splitlines() == [UUID]
        )

        assert backend._checkpoint_task is not None
        assert not backend._checkpoint_task.done()
    finally:
        await backend.on_server_shutdown()


async def test_shutdown_stops_periodic_checkpoint_task(
    deployment_dir: Path,
) -> None:
    backend = MemoryBackend(persistence_interval_seconds=60)
    await backend.on_server_startup(host="localhost")
    task = backend._checkpoint_task

    assert task is not None
    assert not task.done()

    await backend.on_server_shutdown()

    assert backend._checkpoint_task is None
    assert task.done()
