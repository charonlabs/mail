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
        logger.warning(f"MAIL_CONFIG_PATH set to {candidate} but file missing")

    cwd_candidate = Path.cwd() / "mail.toml"
    if cwd_candidate.is_file():
        return cwd_candidate

    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "mail.toml"
        if candidate.is_file():
            return candidate

    return None


@lru_cache(maxsize=1)
def _load_defaults_from_toml() -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Read default server + swarm fields from `mail.toml` if available.
    """

    server_defaults: dict[str, Any] = {
        "port": 8000,
        "host": "0.0.0.0",
        "reload": False,
    }
    swarm_defaults: dict[str, Any] = {
        "name": "example-no-proxy",
        "source": "swarms.json",
        "registry_file": "registries/example-no-proxy.json",
    }

    if tomllib is None:
        logger.warning("tomllib not available; using built-in defaults")
        return server_defaults, swarm_defaults

    config_path = _resolve_mail_config_path()
    if config_path is None:
        logger.warning("mail.toml not found; using built-in defaults")
        return server_defaults, swarm_defaults

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except Exception as e:  # pragma: no cover - uncommon failure
        logger.warning(f"failed to load {config_path}: {e}")
        return server_defaults, swarm_defaults

    server_section = raw_config.get("server")
    if isinstance(server_section, dict):
        server_defaults = {
            "port": server_section.get("port", server_defaults["port"]),
            "host": server_section.get("host", server_defaults["host"]),
            "reload": server_section.get("reload", server_defaults["reload"]),
        }

        swarm_section = server_section.get("swarm")
        if isinstance(swarm_section, dict):
            registry_value = swarm_section.get("registry")
            if registry_value is None:
                registry_value = swarm_section.get("registry_file")

            swarm_defaults = {
                "name": swarm_section.get("name", swarm_defaults["name"]),
                "source": swarm_section.get("source", swarm_defaults["source"]),
                "registry_file": registry_value or swarm_defaults["registry_file"],
            }

    logger.info(
        f"server defaults resolved to {server_defaults} with swarm defaults {swarm_defaults}",
    )
    return server_defaults, swarm_defaults


def _server_defaults() -> dict[str, Any]:
    return _load_defaults_from_toml()[0]


def _swarm_defaults() -> dict[str, Any]:
    return _load_defaults_from_toml()[1]


class SwarmConfig(BaseModel):
    name: str = Field(default_factory=lambda: _swarm_defaults()["name"])
    source: str = Field(default_factory=lambda: _swarm_defaults()["source"])
    registry_file: str = Field(
        default_factory=lambda: _swarm_defaults()["registry_file"]
    )


class ServerConfig(BaseModel):
    port: int = Field(default_factory=lambda: _server_defaults()["port"])
    host: str = Field(default_factory=lambda: _server_defaults()["host"])
    reload: bool = Field(default_factory=lambda: _server_defaults()["reload"])

    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
