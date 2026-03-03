# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import uvicorn
from fastapi import FastAPI

from mail.protocol.constants import MAIL_DEFAULT_PORT


class MAILServer:
    """
    A MAIL HTTP server.
    """
    def __init__(
        self,
        name: str,
        host: str = "127.0.0.1",
        port: int = MAIL_DEFAULT_PORT,
        reload: bool = False,
        description: str = "A MAIL HTTP server.",
        keywords: list[str] = [],
    ) -> None:
        self.name = name
        self.host = host
        self.port = port
        self.reload = reload
        self.description = description
        self.keywords = keywords

        app = FastAPI(
            title=name,
            description=description,
            keywords=keywords,
        )
        self.app = app

    def run(
        self,
    ) -> None:
        """
        Run this server.
        """
        uvicorn.run(self.app, host=self.host, port=self.port, reload=self.reload)

        