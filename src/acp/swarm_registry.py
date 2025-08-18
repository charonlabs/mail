"""
Swarm Registry for interswarm communication.
This module provides service discovery and endpoint management for ACP swarms.
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, TypedDict
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger("acp.swarm_registry")


class SwarmEndpoint(TypedDict):
    """Represents a swarm endpoint for interswarm communication."""

    swarm_name: str
    """The name of the swarm."""

    base_url: str
    """The base URL of the swarm (e.g., https://swarm1.example.com)."""

    health_check_url: str
    """The health check endpoint URL."""

    auth_token_ref: Optional[str] = None
    """Authentication token reference (environment variable or actual token)."""

    last_seen: Optional[datetime] = None
    """When this swarm was last seen/heard from."""

    is_active: bool = True
    """Whether this swarm is currently active."""

    metadata: Optional[Dict] = None
    """Additional metadata about the swarm."""

    volatile: bool = True
    """Whether this swarm is volatile (will be removed from the registry when the server shuts down)."""


class SwarmRegistry:
    """
    Registry for managing swarm endpoints and service discovery.
    """

    def __init__(
        self,
        local_swarm_name: str,
        local_base_url: str,
        persistence_file: Optional[str] = None,
    ):
        self.local_swarm_name = local_swarm_name
        self.local_base_url = local_base_url
        self.endpoints: dict[str, SwarmEndpoint] = {}
        self.health_check_interval = 30  # seconds
        self.health_check_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.persistence_file = persistence_file or "swarm_registry.json"

        # Register self
        self.register_local_swarm(local_base_url)

        # Load persistent endpoints if they exist
        self.load_persistent_endpoints()

    def register_local_swarm(self, base_url: str) -> None:
        """Register the local swarm in the registry."""
        self.endpoints[self.local_swarm_name] = SwarmEndpoint(
            swarm_name=self.local_swarm_name,
            base_url=base_url,
            health_check_url=f"{base_url}/health",
            last_seen=datetime.now(),
            is_active=True,
            volatile=False,  # Local swarm is never volatile
        )
        logger.info(f"Registered local swarm: {self.local_swarm_name} at {base_url}")

    def register_swarm(
        self,
        swarm_name: str,
        base_url: str,
        auth_token: Optional[str] = None,
        metadata: Optional[Dict] = None,
        volatile: bool = True,
    ) -> None:
        """Register a remote swarm in the registry."""
        if swarm_name == self.local_swarm_name:
            logger.warning(f"Attempted to register local swarm {swarm_name} as remote")
            return

        # Automatically convert auth token to environment variable reference if it's a persistent swarm
        if not volatile:
            auth_token_ref = self._get_auth_token_ref(swarm_name, auth_token)
        else:
            auth_token_ref = auth_token

        self.endpoints[swarm_name] = SwarmEndpoint(
            swarm_name=swarm_name,
            base_url=base_url,
            health_check_url=f"{base_url}/health",
            auth_token_ref=auth_token_ref,
            last_seen=datetime.now(),
            is_active=True,
            metadata=metadata,
            volatile=volatile,
        )
        logger.info(
            f"Registered remote swarm: {swarm_name} at {base_url} (volatile: {volatile})"
        )

        # Save persistent endpoints if this swarm is non-volatile
        if not volatile:
            self.save_persistent_endpoints()

    def unregister_swarm(self, swarm_name: str) -> None:
        """Unregister a swarm from the registry."""
        if swarm_name in self.endpoints:
            # Check if this was a persistent swarm
            was_persistent = not self.endpoints[swarm_name].get("volatile", True)

            del self.endpoints[swarm_name]
            logger.info(f"Unregistered swarm: {swarm_name}")

            # Update persistence file if we removed a persistent swarm
            if was_persistent:
                self.save_persistent_endpoints()

    def get_swarm_endpoint(self, swarm_name: str) -> Optional[SwarmEndpoint]:
        """Get the endpoint for a specific swarm."""
        return self.endpoints.get(swarm_name)

    def get_resolved_auth_token(self, swarm_name: str) -> Optional[str]:
        """Get the resolved authentication token for a swarm (resolves environment variable references)."""
        endpoint = self.endpoints.get(swarm_name)
        if not endpoint:
            return None

        return self._resolve_auth_token_ref(endpoint.get("auth_token_ref"))

    def get_all_endpoints(self) -> Dict[str, SwarmEndpoint]:
        """Get all registered endpoints."""
        return self.endpoints.copy()

    def get_active_endpoints(self) -> Dict[str, SwarmEndpoint]:
        """Get all active endpoints."""
        return {
            name: endpoint
            for name, endpoint in self.endpoints.items()
            if endpoint["is_active"]
        }

    def get_persistent_endpoints(self) -> Dict[str, SwarmEndpoint]:
        """Get all non-volatile (persistent) endpoints."""
        return {
            name: endpoint
            for name, endpoint in self.endpoints.items()
            if not endpoint.get("volatile", True)
        }

    def save_persistent_endpoints(self) -> None:
        """Save non-volatile endpoints to the persistence file."""
        try:
            persistent_endpoints = self.get_persistent_endpoints()

            # Convert to serializable format
            data = {
                "local_swarm_name": self.local_swarm_name,
                "local_base_url": self.local_base_url,
                "endpoints": {
                    name: {
                        "swarm_name": endpoint["swarm_name"],
                        "base_url": endpoint["base_url"],
                        "health_check_url": endpoint["health_check_url"],
                        "auth_token_ref": self._get_auth_token_ref(
                            endpoint.get("swarm_name"), endpoint.get("auth_token_ref")
                        ),
                        "last_seen": endpoint["last_seen"].isoformat()
                        if endpoint["last_seen"]
                        else None,
                        "is_active": endpoint["is_active"],
                        "metadata": endpoint.get("metadata"),
                        "volatile": endpoint.get("volatile", True),
                    }
                    for name, endpoint in persistent_endpoints.items()
                },
            }

            with open(self.persistence_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(
                f"Saved {len(persistent_endpoints)} persistent endpoints to {self.persistence_file}"
            )

        except Exception as e:
            logger.error(f"Failed to save persistent endpoints: {e}")

    def _get_auth_token_ref(
        self, swarm_name: str, auth_token: Optional[str]
    ) -> Optional[str]:
        """Convert an auth token to an environment variable reference if it exists."""
        if not auth_token:
            return None

        # Check if this token is already an env var reference
        if auth_token.startswith("${") and auth_token.endswith("}"):
            return auth_token

        # For persistent swarms, automatically convert to environment variable reference
        # Generate a unique environment variable name based on the swarm name
        env_var_name = f"SWARM_AUTH_TOKEN_{swarm_name.upper().replace('-', '_')}"

        logger.info(
            f"Converting auth token to environment variable reference: ${{{env_var_name}}}"
        )
        logger.info(
            f"Please set the environment variable {env_var_name} with the actual token value"
        )

        return f"${{{env_var_name}}}"

    def _resolve_auth_token_ref(self, auth_token_ref: Optional[str]) -> Optional[str]:
        """Resolve an auth token reference to its actual value."""
        if not auth_token_ref:
            return None

        # If it's an environment variable reference, resolve it
        if auth_token_ref.startswith("${") and auth_token_ref.endswith("}"):
            env_var = auth_token_ref[2:-1]  # Remove ${ and }
            resolved_token = os.getenv(env_var)
            if resolved_token:
                logger.debug(f"Resolved auth token from environment variable {env_var}")
                return resolved_token
            else:
                logger.warning(
                    f"Environment variable {env_var} not found for auth token reference"
                )
                return None

        # If it's not a reference, return as-is (for backward compatibility)
        return auth_token_ref

    def migrate_auth_tokens_to_env_refs(
        self, env_var_prefix: str = "SWARM_AUTH_TOKEN"
    ) -> None:
        """Migrate existing auth tokens to environment variable references."""
        migrated_count = 0

        for name, endpoint in self.endpoints.items():
            if name == self.local_swarm_name:
                continue

            auth_token = endpoint.get("auth_token_ref")
            if auth_token and not auth_token.startswith("${"):
                # Create environment variable name
                env_var_name = f"{env_var_prefix}_{name.upper().replace('-', '_')}"

                # Update the endpoint to use the reference
                endpoint["auth_token_ref"] = f"${{{env_var_name}}}"
                migrated_count += 1

                logger.info(
                    f"Migrated auth token for {name} to environment variable reference: ${{{env_var_name}}}"
                )
                logger.info(
                    f"Please set the environment variable {env_var_name} with the actual token value"
                )

        if migrated_count > 0:
            # Save the updated registry
            self.save_persistent_endpoints()
            logger.info(
                f"Migrated {migrated_count} auth tokens to environment variable references"
            )
        else:
            logger.info("No auth tokens to migrate")

    def validate_environment_variables(self) -> Dict[str, bool]:
        """Validate that all required environment variables for auth tokens are set."""
        validation_results = {}

        for name, endpoint in self.endpoints.items():
            if name == self.local_swarm_name:
                continue

            auth_token = endpoint.get("auth_token_ref")
            if auth_token and auth_token.startswith("${") and auth_token.endswith("}"):
                env_var = auth_token[2:-1]
                is_set = os.getenv(env_var) is not None
                validation_results[env_var] = is_set

                if not is_set:
                    logger.warning(
                        f"Environment variable {env_var} for swarm {name} is not set"
                    )

        return validation_results

    def load_persistent_endpoints(self) -> None:
        """Load non-volatile endpoints from the persistence file."""
        try:
            if not os.path.exists(self.persistence_file):
                logger.info(f"No persistence file found at {self.persistence_file}")
                return

            with open(self.persistence_file, "r") as f:
                data = json.load(f)

            # Only load endpoints that aren't already registered
            loaded_count = 0
            for name, endpoint_data in data.get("endpoints", {}).items():
                if name not in self.endpoints and name != self.local_swarm_name:
                    # Resolve auth token reference
                    auth_token = self._resolve_auth_token_ref(
                        endpoint_data.get("auth_token_ref")
                    )

                    endpoint = SwarmEndpoint(
                        swarm_name=endpoint_data["swarm_name"],
                        base_url=endpoint_data["base_url"],
                        health_check_url=endpoint_data["health_check_url"],
                        auth_token_ref=auth_token,
                        last_seen=datetime.fromisoformat(endpoint_data["last_seen"])
                        if endpoint_data["last_seen"]
                        else None,
                        is_active=endpoint_data["is_active"],
                        metadata=endpoint_data.get("metadata"),
                        volatile=endpoint_data.get("volatile", True),
                    )
                    self.endpoints[name] = endpoint
                    loaded_count += 1

            logger.info(
                f"Loaded {loaded_count} persistent endpoints from {self.persistence_file}"
            )

        except Exception as e:
            logger.error(f"Failed to load persistent endpoints: {e}")

    def cleanup_volatile_endpoints(self) -> None:
        """Remove all volatile endpoints from the registry."""
        volatile_endpoints = [
            name
            for name, endpoint in self.endpoints.items()
            if endpoint.get("volatile", True) and name != self.local_swarm_name
        ]

        for name in volatile_endpoints:
            del self.endpoints[name]

        logger.info(f"Cleaned up {len(volatile_endpoints)} volatile endpoints")

        # Save the remaining persistent endpoints
        self.save_persistent_endpoints()

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

    async def _check_swarm_health(
        self, swarm_name: str, endpoint: SwarmEndpoint
    ) -> None:
        """Check the health of a specific swarm."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(
                endpoint["health_check_url"], timeout=timeout
            ) as response:
                if response.status == 200:
                    endpoint["last_seen"] = datetime.now()
                    if not endpoint["is_active"]:
                        endpoint["is_active"] = True
                        logger.info(f"Swarm {swarm_name} is now active")
                else:
                    if endpoint["is_active"]:
                        endpoint["is_active"] = False
                        logger.warning(
                            f"Swarm {swarm_name} is now inactive (status: {response.status})"
                        )
        except Exception as e:
            if endpoint["is_active"]:
                endpoint["is_active"] = False
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
                        if (
                            swarm_name
                            and base_url
                            and swarm_name != self.local_swarm_name
                        ):
                            self.register_swarm(
                                swarm_name=swarm_name,
                                base_url=base_url,
                                auth_token=swarm_info.get("auth_token"),
                                metadata=swarm_info.get("metadata"),
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
                    "swarm_name": endpoint["swarm_name"],
                    "base_url": endpoint["base_url"],
                    "health_check_url": endpoint["health_check_url"],
                    "auth_token_ref": self._get_auth_token_ref(
                        endpoint.get("swarm_name"), endpoint.get("auth_token_ref")
                    ),
                    "last_seen": endpoint["last_seen"].isoformat()
                    if endpoint["last_seen"]
                    else None,
                    "is_active": endpoint["is_active"],
                    "metadata": endpoint.get("metadata"),
                    "volatile": endpoint.get("volatile", True),
                }
                for name, endpoint in self.endpoints.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SwarmRegistry":
        """Create registry from dictionary."""
        registry = cls(data["local_swarm_name"], data["local_base_url"])

        for name, endpoint_data in data["endpoints"].items():
            # Handle both old format (auth_token) and new format (auth_token_ref)
            auth_token = None
            if "auth_token_ref" in endpoint_data:
                auth_token = registry._resolve_auth_token_ref(
                    endpoint_data["auth_token_ref"]
                )
            elif "auth_token" in endpoint_data:
                # Backward compatibility
                auth_token = endpoint_data["auth_token"]

            endpoint = SwarmEndpoint(
                swarm_name=endpoint_data["swarm_name"],
                base_url=endpoint_data["base_url"],
                health_check_url=endpoint_data["health_check_url"],
                auth_token_ref=auth_token,
                last_seen=datetime.fromisoformat(endpoint_data["last_seen"])
                if endpoint_data["last_seen"]
                else None,
                is_active=endpoint_data["is_active"],
                metadata=endpoint_data.get("metadata"),
                volatile=endpoint_data.get("volatile", True),
            )
            registry.endpoints[name] = endpoint

        return registry
