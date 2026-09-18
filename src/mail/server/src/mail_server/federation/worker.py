# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Cancellable durable queue worker for outbound Federation v1 delivery."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from mail_server.federation.outbound import OutboundFederationService
from mail_server.federation.records import OutboundFederationDelivery

if TYPE_CHECKING:
    from mail_server.backends.base import MAILServerBackend

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]


class FederationWorker:
    """Claim bounded batches and finish each lease before clean shutdown."""

    def __init__(
        self,
        *,
        backend: MAILServerBackend,
        outbound: OutboundFederationService,
        poll_interval_seconds: float = 1.0,
        batch_size: int = 20,
        lease_duration: timedelta = timedelta(seconds=30),
        clock: Clock = lambda: datetime.now(UTC),
        sleeper: Sleeper = asyncio.sleep,
        worker_id: str | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("federation worker poll interval must be positive")
        if batch_size <= 0:
            raise ValueError("federation worker batch size must be positive")
        if lease_duration <= timedelta(0):
            raise ValueError("federation worker lease duration must be positive")
        self.backend = backend
        self.outbound = outbound
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self.lease_duration = lease_duration
        self.clock = clock
        self.sleeper = sleeper
        self.worker_id = worker_id or f"federation-{uuid4()}"
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("federation worker clock must be timezone-aware")
        return value.astimezone(UTC)

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("federation worker is already started")
        self._task = asyncio.create_task(
            self.run(),
            name=f"mail-{self.worker_id}",
        )

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _process_one(self, delivery: OutboundFederationDelivery) -> None:
        try:
            await self.outbound.process(delivery, lease_owner=self.worker_id)
        except Exception:
            # The short lease remains durable and recoverable. Do not mutate it
            # blindly after a repository/lease error.
            logger.exception(
                "federation worker failed: envelope_id=%s destination=%s",
                delivery.envelope_id,
                delivery.destination_host,
            )

    async def run_once(self) -> int:
        now = self._now()
        queue_depth = await self.backend.count_active_federation_deliveries()
        claimed = await self.backend.claim_due_federation_deliveries(
            now=now,
            lease_owner=self.worker_id,
            lease_duration=self.lease_duration,
            limit=self.batch_size,
        )
        logger.info(
            "federation queue poll: worker=%s queue_depth=%d claimed=%d",
            self.worker_id,
            queue_depth,
            len(claimed),
        )
        if claimed:
            await asyncio.gather(*(self._process_one(item) for item in claimed))
        return len(claimed)

    async def run(self) -> None:
        logger.info("federation worker started: worker=%s", self.worker_id)
        try:
            while not self._stopping.is_set():
                try:
                    await self.run_once()
                except Exception:
                    logger.exception(
                        "federation worker poll failed: worker=%s", self.worker_id
                    )
                if self._stopping.is_set():
                    break
                sleep_task = asyncio.create_task(
                    self.sleeper(self.poll_interval_seconds)
                )
                stop_task = asyncio.create_task(self._stopping.wait())
                done, pending = await asyncio.wait(
                    {sleep_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    await task
        finally:
            logger.info("federation worker stopped: worker=%s", self.worker_id)
