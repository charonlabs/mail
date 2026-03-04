# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from mail_server.api import MAILServer

server = MAILServer(
    name="Example MAIL Server"
)


def main():
    server.run()


if __name__ == "__main__":
    main()