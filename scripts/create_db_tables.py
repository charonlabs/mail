# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mail",
# ]
# ///

# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

"""
Script to create the necessary database tables for MAIL agent history persistence.

Usage:
    uv run scripts/create_db_tables.py

Alternatively, use the CLI:
    uv run mail db-init

Requires DATABASE_URL environment variable to be set (can be in .env file).
"""

import asyncio

from mail.db.init import create_tables

if __name__ == "__main__":
    asyncio.run(create_tables())
