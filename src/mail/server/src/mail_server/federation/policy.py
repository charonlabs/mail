# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Local peer-acceptance policy for Federation v1."""

from __future__ import annotations

from mail_server.federation.config import FederationConfig


def accepts_federation_peer(config: FederationConfig, sender_host: str) -> bool:
    """Return whether a signature-verified origin passes local policy."""

    normalized = sender_host.encode("idna").decode("ascii").lower()
    if config.policy == "open":
        return True
    if config.policy == "closed":
        return False
    return normalized in config.allowlist
