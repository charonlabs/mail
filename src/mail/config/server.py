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
def _load_defaults_from_toml() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Read default server + swarm fields from `mail.toml` if available.
    """

    server_defaults: dict[str, Any] = {
        "port": 8000,
        "host": "0.0.0.0",
        "reload": False,
        "debug": False,
    }
    swarm_defaults: dict[str, Any] = {
        "name": "example-no-proxy",
        "source": "swarms.json",
        "registry_file": "registries/example-no-proxy.json",
        "description": "",
        "keywords": [],
        "public": False,
    }
    settings_defaults: dict[str, Any] = {
        "task_message_limit": 15,
    }

    if tomllib is None:
        logger.warning("tomllib not available; using built-in defaults")
        return server_defaults, swarm_defaults, settings_defaults

    config_path = _resolve_mail_config_path()
    if config_path is None:
        logger.warning("mail.toml not found; using built-in defaults")
        return server_defaults, swarm_defaults, settings_defaults

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except Exception as e:  # pragma: no cover - uncommon failure
        logger.warning(f"failed to load {config_path}: {e}")
        return server_defaults, swarm_defaults, settings_defaults

    server_section = raw_config.get("server")
    if isinstance(server_section, dict):
        server_defaults = {
            "port": server_section.get("port", server_defaults["port"]),
            "host": server_section.get("host", server_defaults["host"]),
            "reload": server_section.get("reload", server_defaults["reload"]),
            "debug": server_section.get("debug", server_defaults["debug"]),
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
                "description": swarm_section.get(
                    "description", swarm_defaults["description"]
                ),
                "keywords": swarm_section.get("keywords", swarm_defaults["keywords"]),
                "public": swarm_section.get("public", swarm_defaults["public"]),
            }

            settings_section = server_section.get("settings")
            if isinstance(settings_section, dict):
                settings_defaults = {
                    "task_message_limit": settings_section.get(
                        "task_message_limit", settings_defaults["task_message_limit"]
                    ),
                }

    logger.info(
        f"server defaults resolved to {server_defaults} with swarm defaults {swarm_defaults}",
    )
    return server_defaults, swarm_defaults, settings_defaults


def _server_defaults() -> dict[str, Any]:
    return _load_defaults_from_toml()[0]


def _swarm_defaults() -> dict[str, Any]:
    return _load_defaults_from_toml()[1]


def _settings_defaults() -> dict[str, Any]:
    return _load_defaults_from_toml()[2]


class SwarmConfig(BaseModel):
    name: str = Field(default_factory=lambda: _swarm_defaults()["name"])
    description: str = Field(default_factory=lambda: _swarm_defaults()["description"])
    keywords: list[str] = Field(default_factory=lambda: _swarm_defaults()["keywords"])
    public: bool = Field(default_factory=lambda: _swarm_defaults()["public"])
    source: str = Field(default_factory=lambda: _swarm_defaults()["source"])
    registry_file: str = Field(
        default_factory=lambda: _swarm_defaults()["registry_file"]
    )


class SettingsConfig(BaseModel):
    task_message_limit: int = Field(
        default_factory=lambda: _settings_defaults()["task_message_limit"]
    )


class ServerConfig(BaseModel):
    port: int = Field(default_factory=lambda: _server_defaults()["port"])
    host: str = Field(default_factory=lambda: _server_defaults()["host"])
    reload: bool = Field(default_factory=lambda: _server_defaults()["reload"])
    debug: bool = Field(default_factory=lambda: _server_defaults()["debug"])

    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
