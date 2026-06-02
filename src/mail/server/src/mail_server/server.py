# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import logging
import os
import time
from argparse import Namespace
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from mail_protocol.network.responses import HealthGetResponse, RootGetResponse

from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
from mail_server.logging import init_logger
from mail_server.routers import (
    admin,
    auth,
    daemon,
    drafts,
    inbox,
    outbox,
    swarms,
    trash,
)
from mail_server.utils import get_mail_protocol_version

HOST = os.getenv("MAIL_HOST")
if HOST is None:
    raise RuntimeError("env var MAIL_HOST must be set")

logger = logging.getLogger(__name__)

_backend: MAILServerBackend = None  # type: ignore


async def _server_startup(app: FastAPI):
    """
    Handle server startup events.
    """

    logger.info("server starting up...")

    global _backend
    await _backend.on_server_startup(host=HOST)
    app.state.backend = _backend

    app.state.time_start = time.time()

    logger.info("server startup complete")


async def _server_shutdown(app: FastAPI):
    """
    Handle server shutdown events.
    """

    logger.info("server shutting down...")

    await app.state.backend.on_server_shutdown()

    logger.info("server shutdown complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _server_startup(app)

    yield

    await _server_shutdown(app)


app = FastAPI(
    title="MAIL",
    summary="Multi-Agent Interface Layer",
    description="An email system for humans and agents alike",
    lifespan=lifespan,
    version=get_mail_protocol_version(),
)

# Routers for sub-endpoint groups
app.include_router(auth.router)
app.include_router(swarms.router)
app.include_router(inbox.router)
app.include_router(outbox.router)
app.include_router(drafts.router)
app.include_router(trash.router)
app.include_router(daemon.router)
app.include_router(admin.router)


#
# Server endpoints
#
@app.get(
    "/",
    summary="Get basic server information and metadata",
    response_model=RootGetResponse,
)
async def get_root() -> RootGetResponse:
    uptime = time.time() - app.state.time_start
    return RootGetResponse(
        protocol_name="mail",
        protocol_version="2.0",
        uptime=uptime,
    )


@app.get(
    "/health",
    summary="Get the current MAIL server health",
    response_model=HealthGetResponse,
)
async def get_health() -> HealthGetResponse:
    return HealthGetResponse(status="ok")


#
# End of endpoints
#


def run_server(args: Namespace) -> None:
    """
    Run the MAIL server from the CLI.
    """

    match args.backend:
        case "memory" | "mem":
            global _backend
            _backend = MemoryBackend()
        case _:
            raise ValueError(f"invalid backend type: {args.backend}")

    init_logger()

    uvicorn.run(app, host=args.host, port=args.port, log_config=None)
