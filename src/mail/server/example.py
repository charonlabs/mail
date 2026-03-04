# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from mail.server.api import MAILServer

server = MAILServer(
    name="Example MAIL Server"
)

if __name__ == "__main__":
    server.run()