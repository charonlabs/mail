# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from argparse import Namespace

import uvicorn
from fastapi import FastAPI

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

app = FastAPI(
    title="MAIL",
    summary="Multi-Agent Interface Layer",
    description="An email system for humans and agents alike",
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

    uvicorn.run(app, host=args.host, port=args.port)
