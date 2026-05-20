# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from argparse import Namespace
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from mail_server.backends.base import MAILServerBackend
from mail_server.backends.memory.api import MemoryBackend
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

_backend: MAILServerBackend = None  # type: ignore


async def _server_startup(app: FastAPI):
    """
    Handle server startup events.
    """

    global _backend
    await _backend.on_server_startup()
    app.state.backend = _backend


async def _server_shutdown(app: FastAPI):
    """
    Handle server shutdown events.
    """

    await app.state.backend.on_server_shutdown()


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
)

# Routers for sub-endpoint groups
app.include_router(auth.router)
app.include_router(swarms.router)
app.include_router(inbox.router)
app.include_router(outbox.router)
app.include_router(drafts.router)
app.include_router(trash.router)
app.include_router(admin.router)
app.include_router(daemon.router)


#
# Server endpoints
#
@app.get("/")
async def get_root():
    return {"message": "Hello, world!"}


@app.get("/health")
async def get_health():
    return {"status": "ok"}


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

    uvicorn.run(app, host=args.host, port=args.port)
