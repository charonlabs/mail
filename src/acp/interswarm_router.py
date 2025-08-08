"""
Interswarm Router for ACP.
This module handles routing messages between different ACP swarms via HTTP.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import aiohttp
import json

from .message import (
    ACPMessage, 
    ACPInterswarmMessage, 
    parse_agent_address, 
    format_agent_address
)
from .swarm_registry import SwarmRegistry, SwarmEndpoint

logger = logging.getLogger("acp.interswarm_router")


class InterswarmRouter:
    """
    Router for handling interswarm message routing via HTTP.
    """
    
    def __init__(self, swarm_registry: SwarmRegistry, local_swarm_name: str):
        self.swarm_registry = swarm_registry
        self.local_swarm_name = local_swarm_name
        self.session: Optional[aiohttp.ClientSession] = None
        self.message_handlers: Dict[str, callable] = {}
        
    async def start(self) -> None:
        """Start the interswarm router."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        logger.info(f"Started interswarm router for swarm: {self.local_swarm_name}")
    
    async def stop(self) -> None:
        """Stop the interswarm router."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info(f"Stopped interswarm router for swarm: {self.local_swarm_name}")
    
    def register_message_handler(self, message_type: str, handler: callable) -> None:
        """Register a handler for a specific message type."""
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    async def route_message(self, message: ACPMessage) -> bool:
        """
        Route a message to the appropriate destination (local or remote).
        
        Returns:
            bool: True if message was routed successfully, False otherwise
        """
        try:
            # Determine if this is an interswarm message
            msg_content = message["message"]
            
            # Check if recipient is in interswarm format
            if "recipient" in msg_content:
                recipient = msg_content["recipient"]
                recipient_agent, recipient_swarm = parse_agent_address(recipient)
                
                # If recipient is in a different swarm, route via HTTP
                if recipient_swarm and recipient_swarm != self.local_swarm_name:
                    return await self._route_to_remote_swarm(message, recipient_swarm)
                else:
                    # Local message, handle normally
                    return await self._route_to_local_agent(message)
            
            # Check if recipients list contains interswarm addresses
            elif "recipients" in msg_content:
                recipients = msg_content["recipients"]
                local_recipients = []
                remote_routes = {}
                
                for recipient in recipients:
                    recipient_agent, recipient_swarm = parse_agent_address(recipient)
                    
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
                    local_message = self._create_local_message(message, local_recipients)
                    await self._route_to_local_agent(local_message)
                
                # Route to remote swarms
                success = True
                for swarm_name, agents in remote_routes.items():
                    remote_message = self._create_remote_message(message, agents, swarm_name)
                    if not await self._route_to_remote_swarm(remote_message, swarm_name):
                        success = False
                
                return success
            
            else:
                # No recipients found
                logger.error("Message has no recipients")
                return False
                
        except Exception as e:
            logger.error(f"Error routing message: {e}")
            return False
    
    async def _route_to_local_agent(self, message: ACPMessage) -> bool:
        """Route a message to a local agent."""
        try:
            # This will be handled by the local ACP system
            # We need to register a handler that the core ACP can call
            if "local_message_handler" in self.message_handlers:
                await self.message_handlers["local_message_handler"](message)
                return True
            else:
                logger.warning("No local message handler registered")
                return False
        except Exception as e:
            logger.error(f"Error routing to local agent: {e}")
            return False
    
    async def _route_to_remote_swarm(self, message: ACPMessage, swarm_name: str) -> bool:
        """Route a message to a remote swarm via HTTP."""
        try:
            endpoint = self.swarm_registry.get_swarm_endpoint(swarm_name)
            if not endpoint:
                logger.error(f"Unknown swarm endpoint: {swarm_name}")
                return False
            
            if not endpoint.is_active:
                logger.warning(f"Swarm {swarm_name} is not active")
                return False
            
            # Create interswarm message wrapper
            interswarm_message = ACPInterswarmMessage(
                message_id=str(uuid.uuid4()),
                source_swarm=self.local_swarm_name,
                target_swarm=swarm_name,
                timestamp=datetime.now(),
                payload=message["message"],
                auth_token=endpoint.auth_token,
                metadata={
                    "original_message_id": message["id"],
                    "routing_info": message["message"].get("routing_info", {})
                }
            )
            
            # Send via HTTP
            url = f"{endpoint.base_url}/interswarm/message"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"ACP-Interswarm-Router/{self.local_swarm_name}"
            }
            
            if endpoint.auth_token:
                headers["Authorization"] = f"Bearer {endpoint.auth_token}"
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with self.session.post(
                url, 
                json=interswarm_message, 
                headers=headers, 
                timeout=timeout
            ) as response:
                if response.status == 200:
                    logger.info(f"Successfully routed message to swarm: {swarm_name}")
                    return True
                else:
                    logger.error(f"Failed to route message to swarm {swarm_name}: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error routing to remote swarm {swarm_name}: {e}")
            return False
    
    def _create_local_message(self, original_message: ACPMessage, local_recipients: list[str]) -> ACPMessage:
        """Create a local message from an original message with local recipients only."""
        msg_content = original_message["message"].copy()
        
        if "recipients" in msg_content:
            msg_content["recipients"] = local_recipients
        elif "recipient" in msg_content:
            # Convert single recipient to list for local routing
            msg_content["recipients"] = local_recipients
            del msg_content["recipient"]
        
        return ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            message=msg_content,
            msg_type=original_message["msg_type"]
        )
    
    def _create_remote_message(self, original_message: ACPMessage, remote_agents: list[str], swarm_name: str) -> ACPMessage:
        """Create a remote message for a specific swarm."""
        msg_content = original_message["message"].copy()
        
        # Update recipients to use full interswarm addresses
        if "recipients" in msg_content:
            msg_content["recipients"] = [format_agent_address(agent, swarm_name) for agent in remote_agents]
        elif "recipient" in msg_content:
            # Convert to recipients list for remote routing
            msg_content["recipients"] = [format_agent_address(agent, swarm_name) for agent in remote_agents]
            del msg_content["recipient"]
        
        # Add swarm routing information
        msg_content["sender_swarm"] = self.local_swarm_name
        msg_content["recipient_swarm"] = swarm_name
        
        return ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            message=msg_content,
            msg_type=original_message["msg_type"]
        )
    
    async def handle_incoming_interswarm_message(self, interswarm_message: ACPInterswarmMessage) -> bool:
        """Handle an incoming interswarm message from a remote swarm."""
        try:
            # Validate the message
            if interswarm_message["target_swarm"] != self.local_swarm_name:
                logger.error(f"Message intended for {interswarm_message['target_swarm']}, but we are {self.local_swarm_name}")
                return False
            
            # Extract the original ACP message
            original_message = ACPMessage(
                id=interswarm_message["message_id"],
                timestamp=interswarm_message["timestamp"],
                message=interswarm_message["payload"],
                msg_type=self._determine_message_type(interswarm_message["payload"])
            )
            
            # Route to local handler
            if "local_message_handler" in self.message_handlers:
                await self.message_handlers["local_message_handler"](original_message)
                logger.info(f"Successfully handled incoming interswarm message from {interswarm_message['source_swarm']}")
                return True
            else:
                logger.warning("No local message handler registered for incoming interswarm messages")
                return False
                
        except Exception as e:
            logger.error(f"Error handling incoming interswarm message: {e}")
            return False
    
    def _determine_message_type(self, payload: Dict[str, Any]) -> str:
        """Determine the message type from the payload."""
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
    
    async def broadcast_to_all_swarms(self, message: ACPMessage) -> Dict[str, bool]:
        """Broadcast a message to all known swarms."""
        results = {}
        active_endpoints = self.swarm_registry.get_active_endpoints()
        
        for swarm_name, endpoint in active_endpoints.items():
            if swarm_name != self.local_swarm_name:
                results[swarm_name] = await self._route_to_remote_swarm(message, swarm_name)
        
        return results
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        active_endpoints = self.swarm_registry.get_active_endpoints()
        return {
            "local_swarm_name": self.local_swarm_name,
            "total_endpoints": len(self.swarm_registry.get_all_endpoints()),
            "active_endpoints": len(active_endpoints),
            "registered_handlers": list(self.message_handlers.keys())
        }
