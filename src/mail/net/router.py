# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from mail.core.message import (
    MAILAddress,
    MAILInterswarmMessage,
    MAILMessage,
    MAILResponse,
    create_agent_address,
    format_agent_address,
    parse_agent_address,
)

from .registry import SwarmRegistry

logger = logging.getLogger("mail.router")


class InterswarmRouter:
    """
    Router for handling interswarm message routing via HTTP.
    """

    def __init__(self, swarm_registry: SwarmRegistry, local_swarm_name: str):
        self.swarm_registry = swarm_registry
        self.local_swarm_name = local_swarm_name
        self.session: aiohttp.ClientSession | None = None
        self.message_handlers: dict[str, Callable[[MAILMessage], Awaitable[None]]] = {}

    async def start(self) -> None:
        """
        Start the interswarm router.
        """
        if self.session is None:
            self.session = aiohttp.ClientSession()
        logger.info(f"started interswarm router for swarm: '{self.local_swarm_name}'")

    async def stop(self) -> None:
        """
        Stop the interswarm router.
        """
        if self.session:
            await self.session.close()
            self.session = None
        logger.info(f"stopped interswarm router for swarm: '{self.local_swarm_name}'")

    async def is_running(self) -> bool:
        """
        Check if the interswarm router is running.
        """
        return self.session is not None

    def register_message_handler(
        self, message_type: str, handler: Callable[[MAILMessage], Awaitable[None]]
    ) -> None:
        """
        Register a handler for a specific message type.
        """
        self.message_handlers[message_type] = handler
        logger.info(f"registered handler for message type: '{message_type}'")

    async def route_message(self, message: MAILMessage) -> MAILMessage:
        """
        Route a message to the appropriate destination (local or remote).

        Returns:
            MAILMessage: The response to the routed message
        """
        try:
            # Determine if this is an interswarm message
            msg_content = message["message"]

            # Check if recipient is in interswarm format
            if "recipient" in msg_content:
                recipient = msg_content["recipient"]  # type: ignore
                recipient_agent, recipient_swarm = parse_agent_address(
                    recipient["address"]
                )

                # If recipient is in a different swarm, route via HTTP
                if recipient_swarm and recipient_swarm != self.local_swarm_name:
                    response = await self._route_to_remote_swarm(
                        message, recipient_swarm
                    )
                else:
                    # Local message, handle normally
                    response = await self._route_to_local_agent(message)

                return response

            # Check if recipients list contains interswarm addresses
            elif "recipients" in msg_content:
                recipients = msg_content["recipients"]
                local_recipients = []
                remote_routes: dict[str, list[str]] = {}

                for recipient in recipients:
                    recipient_agent, recipient_swarm = parse_agent_address(
                        recipient["address"]
                    )

                    if recipient_swarm and recipient_swarm != self.local_swarm_name:
                        # Remote recipient
                        if recipient_swarm not in remote_routes:
                            remote_routes[recipient_swarm] = []
                        remote_routes[recipient_swarm].append(recipient_agent)
                    else:
                        # Local recipient
                        local_recipients.append(recipient_agent)

                # Route to local recipients
                if local_recipients:
                    local_message = self._create_local_message(
                        message, local_recipients
                    )
                    response = await self._route_to_local_agent(local_message)

                # Route to remote swarms
                for swarm_name, agents in remote_routes.items():
                    remote_message = self._create_remote_message(
                        message, agents, swarm_name
                    )
                    response = await self._route_to_remote_swarm(
                        remote_message, swarm_name
                    )

                return response

            else:
                # No recipients found
                logger.error("message has no recipients")
                return self._system_router_message(message, "message has no recipients")

        except Exception as e:
            logger.error(f"error routing message: '{e}'")
            return self._system_router_message(message, f"error routing message: '{e}'")

    async def _route_to_local_agent(self, message: MAILMessage) -> MAILMessage:
        """
        Route a message to a local agent.
        """
        try:
            # This will be handled by the local MAIL system
            # We need to register a handler that the core MAIL can call
            if "local_message_handler" in self.message_handlers:
                await self.message_handlers["local_message_handler"](message)
                return message
            else:
                logger.warning("no local message handler registered")
                return self._system_router_message(
                    message, "no local message handler registered"
                )
        except Exception as e:
            logger.error(f"error routing to local agent: '{e}'")
            return self._system_router_message(
                message, f"error routing to local agent: '{e}'"
            )

    async def _route_to_remote_swarm(
        self, message: MAILMessage, swarm_name: str
    ) -> MAILMessage:
        """
        Route a message to a remote swarm via HTTP.
        """
        try:
            endpoint = self.swarm_registry.get_swarm_endpoint(swarm_name)
            if not endpoint:
                logger.error(f"unknown swarm endpoint: '{swarm_name}'")
                return self._system_router_message(
                    message, f"unknown swarm endpoint: '{swarm_name}'"
                )

            if not endpoint["is_active"]:
                logger.warning(f"swarm '{swarm_name}' is not active")
                return self._system_router_message(
                    message, f"swarm '{swarm_name}' is not active"
                )

            # Update the message to include the full source agent address
            message["message"]["sender"] = format_agent_address(
                message["message"]["sender"]["address"], self.local_swarm_name
            )

            # Create interswarm message wrapper
            interswarm_message = MAILInterswarmMessage(
                message_id=str(uuid.uuid4()),
                source_swarm=self.local_swarm_name,
                target_swarm=swarm_name,
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                payload=message["message"],
                msg_type=message["msg_type"],  # type: ignore
                auth_token=self.swarm_registry.get_resolved_auth_token(swarm_name),
                metadata={
                    "original_message_id": message["id"],
                    "routing_info": message["message"].get("routing_info", {}),
                    "expect_response": True,
                },
            )

            # Send via HTTP
            url = f"{endpoint['base_url']}/interswarm/message"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
            }

            auth_token = self.swarm_registry.get_resolved_auth_token(swarm_name)
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            timeout = aiohttp.ClientTimeout(total=3600)
            assert self.session is not None
            async with self.session.post(
                url, json=interswarm_message, headers=headers, timeout=timeout
            ) as response:
                if response.status == 200:
                    logger.info(f"successfully routed message to swarm: '{swarm_name}'")
                    response_json = await response.json()
                    return MAILMessage(**response_json)  # type: ignore
                else:
                    logger.error(
                        f"failed to route message to swarm '{swarm_name}' with status: '{response.status}'"
                    )
                    return self._system_router_message(
                        message,
                        f"failed to route message to swarm '{swarm_name}' with status: '{response.status}'",
                    )

        except Exception as e:
            logger.error(
                f"error routing to remote swarm '{swarm_name}' with error: '{e}'"
            )
            return self._system_router_message(
                message,
                f"error routing to remote swarm '{swarm_name}' with error: '{e}'",
            )

    async def handle_incoming_response(self, response_message: MAILMessage) -> bool:
        """
        Handle an incoming response from a remote swarm.
        """
        try:
            # Route the response to the local MAIL instance
            if "local_message_handler" in self.message_handlers:
                await self.message_handlers["local_message_handler"](response_message)
                logger.info(f"successfully handled incoming response from remote swarm")
                return True
            else:
                logger.warning(
                    "no local message handler registered for incoming responses"
                )
                return False

        except Exception as e:
            logger.error(f"error handling incoming response: '{e}'")
            return False

    def _create_local_message(
        self, original_message: MAILMessage, local_recipients: list[str]
    ) -> MAILMessage:
        """
        Create a local message from an original message with local recipients only.
        """
        msg_content = original_message["message"].copy()

        if "recipients" in msg_content:
            msg_content["recipients"] = [  # type: ignore
                create_agent_address(agent) for agent in local_recipients
            ]
        elif "recipient" in msg_content:
            # Convert single recipient to list for local routing
            msg_content["recipients"] = [  # type: ignore
                create_agent_address(agent) for agent in local_recipients
            ]
            del msg_content["recipient"]  # type: ignore

        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=msg_content,
            msg_type=original_message["msg_type"],
        )

    def _create_remote_message(
        self, original_message: MAILMessage, remote_agents: list[str], swarm_name: str
    ) -> MAILMessage:
        """
        Create a remote message for a specific swarm.
        """
        msg_content = original_message["message"].copy()

        # Update recipients to use full interswarm addresses
        if "recipients" in msg_content:
            msg_content["recipients"] = [  # type: ignore
                format_agent_address(agent, swarm_name) for agent in remote_agents
            ]
            msg_content["recipient_swarms"] = [swarm_name]  # type: ignore
        elif "recipient" in msg_content:
            # Convert to recipients list for remote routing
            msg_content["recipients"] = [  # type: ignore
                format_agent_address(agent, swarm_name) for agent in remote_agents
            ]
            msg_content["recipient_swarm"] = swarm_name  # type: ignore
            del msg_content["recipient"]  # type: ignore

        # Add swarm routing information
        msg_content["sender_swarm"] = self.local_swarm_name

        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=msg_content,
            msg_type=original_message["msg_type"],
        )

    async def handle_incoming_interswarm_message(
        self, interswarm_message: MAILInterswarmMessage
    ) -> bool:
        """
        Handle an incoming interswarm message from a remote swarm.
        """
        try:
            # Validate the message
            if interswarm_message["target_swarm"] != self.local_swarm_name:
                logger.error(
                    f"message intended for '{interswarm_message['target_swarm']}', but we are '{self.local_swarm_name}'"
                )
                return False

            # Extract the original MAIL message
            original_message = MAILMessage(
                id=interswarm_message["message_id"],
                timestamp=interswarm_message["timestamp"],
                message=interswarm_message["payload"],
                msg_type=self._determine_message_type(interswarm_message["payload"]),  # type: ignore
            )

            # Route to local handler
            if "local_message_handler" in self.message_handlers:
                await self.message_handlers["local_message_handler"](original_message)
                logger.info(
                    f"successfully handled incoming interswarm message from '{interswarm_message['source_swarm']}'"
                )
                return True
            else:
                logger.warning(
                    "no local message handler registered for incoming interswarm messages"
                )
                return False

        except Exception as e:
            logger.error(f"error handling incoming interswarm message: '{e}'")
            return False

    def _determine_message_type(self, payload: dict[str, Any]) -> str:
        """
        Determine the message type from the payload.
        """
        if "request_id" in payload and "recipient" in payload:
            return "request"
        elif "request_id" in payload and "sender" in payload:
            return "response"
        elif "broadcast_id" in payload:
            return "broadcast"
        elif "interrupt_id" in payload:
            return "interrupt"
        else:
            return "unknown"

    async def broadcast_to_all_swarms(self, message: MAILMessage) -> dict[str, bool]:
        """
        Broadcast a message to all known swarms.
        """
        results: dict[str, bool] = {}
        active_endpoints = self.swarm_registry.get_active_endpoints()

        for swarm_name, endpoint in active_endpoints.items():
            if swarm_name != self.local_swarm_name:
                response = await self._route_to_remote_swarm(message, swarm_name)
                results[swarm_name] = response is not None

        return results

    def get_routing_stats(self) -> dict[str, Any]:
        """
        Get routing statistics.
        """
        active_endpoints = self.swarm_registry.get_active_endpoints()
        return {
            "local_swarm_name": self.local_swarm_name,
            "total_endpoints": len(self.swarm_registry.get_all_endpoints()),
            "active_endpoints": len(active_endpoints),
            "registered_handlers": list(self.message_handlers.keys()),
        }

    def _system_router_message(self, message: MAILMessage, reason: str) -> MAILMessage:
        """
        Create a system router message.
        """
        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILResponse(
                task_id=message["message"]["task_id"],
                request_id=message["message"]["request_id"],  # type: ignore
                sender=MAILAddress(
                    address_type="system",
                    address=self.local_swarm_name,
                ),
                recipient=message["message"]["sender"],  # type: ignore
                subject="Router Error",
                body=reason,
                sender_swarm=self.local_swarm_name,
                recipient_swarm=self.local_swarm_name,
                routing_info={},
            ),
            msg_type="response",
        )
