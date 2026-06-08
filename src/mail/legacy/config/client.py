# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - hard fallback
        tomllib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _resolve_mail_config_path() -> Path | None:
    """
    Determine the best candidate path for `mail.toml`.
    """

    env_path = os.getenv("MAIL_CONFIG_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return candidate
        logger.debug(f"MAIL_CONFIG_PATH set to {candidate} but file missing")

    cwd_candidate = Path.cwd() / "mail.toml"
    if cwd_candidate.is_file():
        return cwd_candidate

    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "mail.toml"
        if candidate.is_file():
            return candidate

    return None


@lru_cache(maxsize=1)
def _client_defaults() -> dict[str, Any]:
    """
    Resolve client defaults from `mail.toml`, falling back to literals.
    """

    defaults: dict[str, Any] = {
        "timeout": 3600.0,
        "verbose": False,
    }

    if tomllib is None:
        logger.debug("tomllib not available; using built-in client defaults")
        return defaults

    config_path = _resolve_mail_config_path()
    if config_path is None:
        logger.debug("mail.toml not found; using built-in client defaults")
        return defaults

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except Exception as e:  # pragma: no cover - uncommon failure
        logger.warning(f"failed to load {config_path}: {e}")
        return defaults

    client_section = raw_config.get("client")
    if isinstance(client_section, dict):
        if "timeout" in client_section:
            defaults["timeout"] = float(client_section["timeout"])
        if "verbose" in client_section:
            defaults["verbose"] = bool(client_section["verbose"])
    return defaults


class ClientConfig(BaseModel):
    timeout: float = Field(default_factory=lambda: _client_defaults()["timeout"])
    verbose: bool = Field(default_factory=lambda: _client_defaults()["verbose"])
