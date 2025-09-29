# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from pydantic import BaseModel


class SwarmConfig(BaseModel):
    name: str = "example-no-proxy"
    source: str = "swarms.json"
    registry_file: str = "registries/example-no-proxy.json"
    

class ServerConfig(BaseModel):
    port: int = 8000
    host: str = "0.0.0.0"
    reload: bool = False

    swarm: SwarmConfig = SwarmConfig()