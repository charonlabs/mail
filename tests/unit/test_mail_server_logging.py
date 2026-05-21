# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

import os
import subprocess
import sys
from datetime import datetime


def test_init_logger_writes_mail_server_and_uvicorn_logs(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)

    script = """
import logging
from mail_server.logging import init_logger

log_path = init_logger()
logging.getLogger("mail_server.server").info("mail server test log")
logging.getLogger("uvicorn.error").info("uvicorn error test log")
logging.getLogger("uvicorn.access").info("uvicorn access test log")
print(log_path)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    today_str = datetime.today().strftime("%Y_%m_%d")
    expected_path = tmp_path / ".mail-swarms" / "server_logs" / f"{today_str}.log"
    assert result.stdout.strip() == str(expected_path)
    assert "mail server test log" in result.stderr
    assert "uvicorn error test log" in result.stderr
    assert "uvicorn access test log" in result.stderr

    log_contents = expected_path.read_text(encoding="utf-8")
    assert "mail server test log" in log_contents
    assert "uvicorn error test log" in log_contents
    assert "uvicorn access test log" in log_contents
