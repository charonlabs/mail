# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

"""
URL scheme parsing for swarm:// URLs.

Supports:
    swarm://connect?server=<host>&token=<api_key>
    swarm://invite?server=<host>&token=<api_key>
"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass
class SwarmURL:
    """Parsed swarm:// URL."""

    action: str  # "connect" or "invite"
    server: str | None = None
    token: str | None = None


def parse_swarm_url(url: str) -> SwarmURL | None:
    """
    Parse a swarm:// URL into its components.

    Args:
        url: The URL to parse (e.g., "swarm://connect?server=example.com&token=abc")

    Returns:
        SwarmURL if the URL is a valid swarm:// URL, None otherwise.
    """
    if not url.startswith("swarm://"):
        return None

    parsed = urlparse(url)

    # For swarm://connect?server=x, parsed.netloc = "connect", parsed.query = "server=x"
    action = parsed.netloc

    if action in ("connect", "invite"):
        params = parse_qs(parsed.query)
        return SwarmURL(
            action=action,
            server=params.get("server", [None])[0],
            token=params.get("token", [None])[0],
        )

    return None
