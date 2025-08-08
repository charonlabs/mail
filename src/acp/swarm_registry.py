"""
Swarm Registry for interswarm communication.
This module provides service discovery and endpoint management for ACP swarms.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from dataclasses import dataclass
import aiohttp
import json

logger = logging.getLogger("acp.swarm_registry")


@dataclass
class SwarmEndpoint:
    """Represents a swarm endpoint for interswarm communication."""
    
    swarm_name: str
    """The name of the swarm."""
    
    base_url: str
    """The base URL of the swarm (e.g., https://swarm1.example.com)."""
    
    health_check_url: str
    """The health check endpoint URL."""
    
    auth_token: Optional[str] = None
    """Authentication token for this swarm."""
    
    last_seen: Optional[datetime] = None
    """When this swarm was last seen/heard from."""
    
    is_active: bool = True
    """Whether this swarm is currently active."""
    
    metadata: Optional[Dict] = None
    """Additional metadata about the swarm."""


class SwarmRegistry:
    """
    Registry for managing swarm endpoints and service discovery.
    """
    
    def __init__(self, local_swarm_name: str, local_base_url: str):
        self.local_swarm_name = local_swarm_name
        self.local_base_url = local_base_url
        self.endpoints: Dict[str, SwarmEndpoint] = {}
        self.health_check_interval = 30  # seconds
        self.health_check_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Register self
        self.register_local_swarm(local_base_url)
    
    def register_local_swarm(self, base_url: str) -> None:
        """Register the local swarm in the registry."""
        self.endpoints[self.local_swarm_name] = SwarmEndpoint(
            swarm_name=self.local_swarm_name,
            base_url=base_url,
            health_check_url=f"{base_url}/health",
            last_seen=datetime.now(),
            is_active=True
        )
        logger.info(f"Registered local swarm: {self.local_swarm_name} at {base_url}")
    
    def register_swarm(self, swarm_name: str, base_url: str, auth_token: Optional[str] = None, metadata: Optional[Dict] = None) -> None:
        """Register a remote swarm in the registry."""
        if swarm_name == self.local_swarm_name:
            logger.warning(f"Attempted to register local swarm {swarm_name} as remote")
            return
            
        self.endpoints[swarm_name] = SwarmEndpoint(
            swarm_name=swarm_name,
            base_url=base_url,
            health_check_url=f"{base_url}/health",
            auth_token=auth_token,
            last_seen=datetime.now(),
            is_active=True,
            metadata=metadata
        )
        logger.info(f"Registered remote swarm: {swarm_name} at {base_url}")
    
    def unregister_swarm(self, swarm_name: str) -> None:
        """Unregister a swarm from the registry."""
        if swarm_name in self.endpoints:
            del self.endpoints[swarm_name]
            logger.info(f"Unregistered swarm: {swarm_name}")
    
    def get_swarm_endpoint(self, swarm_name: str) -> Optional[SwarmEndpoint]:
        """Get the endpoint for a specific swarm."""
        return self.endpoints.get(swarm_name)
    
    def get_all_endpoints(self) -> Dict[str, SwarmEndpoint]:
        """Get all registered endpoints."""
        return self.endpoints.copy()
    
    def get_active_endpoints(self) -> Dict[str, SwarmEndpoint]:
        """Get all active endpoints."""
        return {name: endpoint for name, endpoint in self.endpoints.items() if endpoint.is_active}
    
    async def start_health_checks(self) -> None:
        """Start periodic health checks for all registered swarms."""
        if self.health_check_task is not None:
            return
            
        self.session = aiohttp.ClientSession()
        self.health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Started swarm health check loop")
    
    async def stop_health_checks(self) -> None:
        """Stop periodic health checks."""
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("Stopped swarm health check loop")
    
    async def _health_check_loop(self) -> None:
        """Main health check loop."""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _perform_health_checks(self) -> None:
        """Perform health checks on all remote swarms."""
        if not self.session:
            return
            
        tasks = []
        for swarm_name, endpoint in self.endpoints.items():
            if swarm_name != self.local_swarm_name:
                tasks.append(self._check_swarm_health(swarm_name, endpoint))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_swarm_health(self, swarm_name: str, endpoint: SwarmEndpoint) -> None:
        """Check the health of a specific swarm."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(endpoint.health_check_url, timeout=timeout) as response:
                if response.status == 200:
                    endpoint.last_seen = datetime.now()
                    if not endpoint.is_active:
                        endpoint.is_active = True
                        logger.info(f"Swarm {swarm_name} is now active")
                else:
                    if endpoint.is_active:
                        endpoint.is_active = False
                        logger.warning(f"Swarm {swarm_name} is now inactive (status: {response.status})")
        except Exception as e:
            if endpoint.is_active:
                endpoint.is_active = False
                logger.warning(f"Swarm {swarm_name} is now inactive (error: {e})")
    
    async def discover_swarms(self, discovery_urls: list[str]) -> None:
        """Discover swarms from a list of discovery endpoints."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        tasks = []
        for url in discovery_urls:
            tasks.append(self._discover_from_endpoint(url))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Discovery error: {result}")
    
    async def _discover_from_endpoint(self, url: str) -> None:
        """Discover swarms from a specific endpoint."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(f"{url}/swarms", timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    for swarm_info in data.get("swarms", []):
                        swarm_name = swarm_info.get("name")
                        base_url = swarm_info.get("base_url")
                        if swarm_name and base_url and swarm_name != self.local_swarm_name:
                            self.register_swarm(
                                swarm_name=swarm_name,
                                base_url=base_url,
                                auth_token=swarm_info.get("auth_token"),
                                metadata=swarm_info.get("metadata")
                            )
        except Exception as e:
            logger.error(f"Failed to discover from {url}: {e}")
    
    def to_dict(self) -> Dict:
        """Convert registry to dictionary for serialization."""
        return {
            "local_swarm_name": self.local_swarm_name,
            "local_base_url": self.local_base_url,
            "endpoints": {
                name: {
                    "swarm_name": endpoint.swarm_name,
                    "base_url": endpoint.base_url,
                    "health_check_url": endpoint.health_check_url,
                    "last_seen": endpoint.last_seen.isoformat() if endpoint.last_seen else None,
                    "is_active": endpoint.is_active,
                    "metadata": endpoint.metadata
                }
                for name, endpoint in self.endpoints.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SwarmRegistry":
        """Create registry from dictionary."""
        registry = cls(data["local_swarm_name"], data["local_base_url"])
        
        for name, endpoint_data in data["endpoints"].items():
            endpoint = SwarmEndpoint(
                swarm_name=endpoint_data["swarm_name"],
                base_url=endpoint_data["base_url"],
                health_check_url=endpoint_data["health_check_url"],
                last_seen=datetime.fromisoformat(endpoint_data["last_seen"]) if endpoint_data["last_seen"] else None,
                is_active=endpoint_data["is_active"],
                metadata=endpoint_data.get("metadata")
            )
            registry.endpoints[name] = endpoint
        
        return registry
