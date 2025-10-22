# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

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


StreamHandler = Callable[[str, str | None], Awaitable[None]]


class InterswarmRouter:
    """
    Router for handling interswarm message routing via HTTP.
    """

    def __init__(self, swarm_registry: SwarmRegistry, local_swarm_name: str):
        self.swarm_registry = swarm_registry
        self.local_swarm_name = local_swarm_name
        self.session: aiohttp.ClientSession | None = None
        self.message_handlers: dict[str, Callable[[MAILInterswarmMessage], Awaitable[None]]] = {}

    def _log_prelude(self) -> str:
        """
        Get the log prelude for the router.
        """
        return f"[[green]{self.local_swarm_name}[/green]@{self.swarm_registry.local_base_url}]"

    async def start(self) -> None:
        """
        Start the interswarm router.
        """
        if self.session is None:
            self.session = aiohttp.ClientSession()
        logger.info(f"{self._log_prelude()} started interswarm router")

    async def stop(self) -> None:
        """
        Stop the interswarm router.
        """
        if self.session:
            await self.session.close()
            self.session = None
        logger.info(f"{self._log_prelude()} stopped interswarm router")

    async def is_running(self) -> bool:
        """
        Check if the interswarm router is running.
        """
        return self.session is not None

    def register_message_handler(
        self, message_type: str, handler: Callable[[MAILInterswarmMessage], Awaitable[None]]
    ) -> None:
        """
        Register a handler for a specific message type.
        """
        self.message_handlers[message_type] = handler
        logger.info(
            f"{self._log_prelude()} registered handler for message type: '{message_type}'"
        )

    def _convert_interswarm_message_to_local(
        self,
        message: MAILInterswarmMessage,
    ) -> MAILMessage:
        """
        Convert an interswarm message (`MAILInterswarmMessage`) to a local message (`MAILMessage`).
        """
        return MAILMessage(
            id=message["message_id"],
            timestamp=message["timestamp"],
            message=message["payload"],
            msg_type=message["msg_type"],
        )

    def _resolve_auth_token_ref(self, auth_token_ref: str | None) -> str | None:
        """
        Resolve an auth token reference to an actual token.
        """
        if auth_token_ref is None:
            return None
        return self.swarm_registry.get_resolved_auth_token(auth_token_ref)

    async def receive_interswarm_message_forward(
        self,
        message: MAILInterswarmMessage,
    ) -> None:
        """
        Receive an interswarm message in the case of a new task.
        """
        # ensure this is the right target swarm
        if message["target_swarm"] != self.local_swarm_name:
            logger.error(f"{self._log_prelude()} received interswarm message for wrong swarm: '{message['target_swarm']}'")
            raise ValueError(f"received interswarm message for wrong swarm: '{message['target_swarm']}'")
        
        # attempt to post this message to the local swarm
        try:
            handler = self.message_handlers.get("local_message_handler")
            if handler:
                await handler(message)
            else:
                logger.warning(f"{self._log_prelude()} no local message handler registered")
                raise ValueError("no local message handler registered")
        except Exception as e:
            logger.error(f"{self._log_prelude()} error receiving interswarm message forward: '{e}'")
            raise ValueError(f"error receiving interswarm message forward: '{e}'")

    async def receive_interswarm_message_back(
        self,
        message: MAILInterswarmMessage,
    ) -> None:
        """
        Receive an interswarm message in the case of a task resolution.
        """
        # ensure this is the right target swarm
        if message["target_swarm"] != self.local_swarm_name:
            logger.error(f"{self._log_prelude()} received interswarm message for wrong swarm: '{message['target_swarm']}'")
            raise ValueError(f"received interswarm message for wrong swarm: '{message['target_swarm']}'")
        
        # attempt to post this message to the local swarm
        try:
            handler = self.message_handlers.get("local_message_handler")
            if handler:
                await handler(message)
            else:
                logger.warning(f"{self._log_prelude()} no local message handler registered")
                raise ValueError("no local message handler registered")
        except Exception as e:
            logger.error(f"{self._log_prelude()} error receiving interswarm message back: '{e}'")
            raise ValueError(f"error receiving interswarm message back: '{e}'")

    async def send_interswarm_message_forward(
        self,
        message: MAILInterswarmMessage,
    ) -> None:
        """
        Send a message to a remote swarm in the case of a new task.
        """
        # ensure target swarm is reachable
        endpoint = self.swarm_registry.get_swarm_endpoint(message["target_swarm"])
        if not endpoint:
            logger.error(f"{self._log_prelude()} unknown swarm endpoint: '{message['target_swarm']}'")
            raise ValueError(f"unknown swarm endpoint: '{message['target_swarm']}'")
        
        # ensure the target swarm is active
        if not endpoint["is_active"]:
            logger.error(f"{self._log_prelude()} swarm '{message['target_swarm']}' is not active")
            raise ValueError(f"swarm '{message['target_swarm']}' is not active")
        
        # ensure this session is open
        if self.session is None:
            logger.error(f"{self._log_prelude()} HTTP client session is not open")
            raise ValueError("HTTP client session is not open")

        # attempt to send this message to the remote swarm
        try:
            token = self._resolve_auth_token_ref(endpoint["auth_token_ref"])
            async with self.session.post(
                endpoint["base_url"] + "/interswarm/forward",
                json=message,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                if response.status != 200:
                    logger.error(f"{self._log_prelude()} failed to send interswarm message forward to swarm '{message['target_swarm']}': '{response.status}'")
                    raise ValueError(f"failed to send interswarm message forward to swarm '{message['target_swarm']}': HTTP status code '{response.status}', reason '{response.reason}'")
                else:
                    logger.info(f"{self._log_prelude()} successfully sent interswarm message forward to swarm '{message['target_swarm']}'")
                    return
        except Exception as e:
            logger.error(f"{self._log_prelude()} error sending interswarm message forward: '{e}'")
            raise ValueError(f"error sending interswarm message forward: '{e}'")

    async def send_interswarm_message_back(
        self,
        message: MAILInterswarmMessage,
    ) -> None:
        """
        Send a message to a remote swarm in the case of a task resolution.
        """
        # ensure target swarm is reachable
        endpoint = self.swarm_registry.get_swarm_endpoint(message["target_swarm"])
        if not endpoint:
            logger.error(f"{self._log_prelude()} unknown swarm endpoint: '{message['target_swarm']}'")
            raise ValueError(f"unknown swarm endpoint: '{message['target_swarm']}'")
        
        # ensure the target swarm is active
        if not endpoint["is_active"]:
            logger.error(f"{self._log_prelude()} swarm '{message['target_swarm']}' is not active")
            raise ValueError(f"swarm '{message['target_swarm']}' is not active")
        
        # ensure this session is open
        if self.session is None:
            logger.error(f"{self._log_prelude()} HTTP client session is not open")
            raise ValueError("HTTP client session is not open")

        # attempt to send this message to the remote swarm
        try:
            token = self._resolve_auth_token_ref(endpoint["auth_token_ref"])
            async with self.session.post(
                endpoint["base_url"] + "/interswarm/back",
                json=message,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                if response.status != 200:
                    logger.error(f"{self._log_prelude()} failed to send interswarm message back to swarm '{message['target_swarm']}': '{response.status}'")
                    raise ValueError(f"failed to send interswarm message back to swarm '{message['target_swarm']}': HTTP status code '{response.status}', reason '{response.reason}'")
                else:
                    logger.info(f"{self._log_prelude()} successfully sent interswarm message back to swarm '{message['target_swarm']}'")
                    return
        except Exception as e:
            logger.error(f"{self._log_prelude()} error sending interswarm message back: '{e}'")
            raise ValueError(f"error sending interswarm message back: '{e}'")

    async def post_interswarm_user_message(
        self,
        message: MAILInterswarmMessage,
    ) -> MAILMessage:
        """
        Post a message (from an admin or user) to a remote swarm.
        """
        # ensure target swarm is reachable
        endpoint = self.swarm_registry.get_swarm_endpoint(message["target_swarm"])
        if not endpoint:
            logger.error(f"{self._log_prelude()} unknown swarm endpoint: '{message['target_swarm']}'")
            raise ValueError(f"unknown swarm endpoint: '{message['target_swarm']}'")
        
        # ensure the target swarm is active
        if not endpoint["is_active"]:
            logger.error(f"{self._log_prelude()} swarm '{message['target_swarm']}' is not active")
            raise ValueError(f"swarm '{message['target_swarm']}' is not active")
        
        # ensure this session is open
        if self.session is None:
            logger.error(f"{self._log_prelude()} HTTP client session is not open")
            raise ValueError("HTTP client session is not open")
        
        # attempt to post this message to the remote swarm
        try:
            async with self.session.post(
                endpoint["base_url"] + "/interswarm/message",
                json=message,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
                    "Authorization": f"Bearer {message['auth_token']}",
                },
            ) as response:
                if response.status != 200:
                    logger.error(f"{self._log_prelude()} failed to post interswarm user message to swarm '{message['target_swarm']}': '{response.status}'")
                    raise ValueError(f"failed to post interswarm user message to swarm '{message['target_swarm']}': HTTP status code '{response.status}', reason '{response.reason}'")
                else:
                    logger.info(f"{self._log_prelude()} successfully posted interswarm user message to swarm '{message['target_swarm']}'")
                    return cast(MAILMessage, await response.json())
        except Exception as e:
            logger.error(f"{self._log_prelude()} error posting interswarm user message: '{e}'")
            raise ValueError(f"error posting interswarm user message: '{e}'")

    def convert_local_message_to_interswarm(
        self,
        message: MAILMessage,
        task_owner: str,
        task_contributors: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> MAILInterswarmMessage:
        """
        Convert a local message (`MAILMessage`) to an interswarm message (`MAILInterswarmMessage`).
        """
        all_targets = message.get("recipient_swarms")
        assert isinstance(all_targets, list)
        target_swarm = all_targets[0]
        assert isinstance(target_swarm, str)
        return MAILInterswarmMessage(
            message_id=message["id"],
            source_swarm=self.local_swarm_name,
            target_swarm=target_swarm,
            timestamp=message["timestamp"],
            payload=message["message"],
            msg_type=message["msg_type"], # type: ignore
            auth_token=self.swarm_registry.get_resolved_auth_token(target_swarm),
            task_owner=task_owner,
            task_contributors=task_contributors,
            metadata=metadata or {},
        )

    # async def route_message(
    #     self,
    #     message: MAILMessage,
    #     *,
    #     stream_handler: StreamHandler | None = None,
    #     ignore_stream_pings: bool = False,
    # ) -> MAILMessage:
    #     """
    #     Route a message to the appropriate destination (local or remote).

    #     Returns:
    #         MAILMessage: The response to the routed message
    #     """
    #     try:
    #         # Determine if this is an interswarm message
    #         msg_content = message["message"]

    #         # Check if recipient is in interswarm format
    #         routing_info = msg_content.get("routing_info")
    #         stream_requested = isinstance(routing_info, dict) and bool(
    #             routing_info.get("stream")
    #         )
    #         ignore_pings_flag = isinstance(routing_info, dict) and bool(
    #             routing_info.get("ignore_stream_pings")
    #         )
    #         ignore_pings = ignore_stream_pings or ignore_pings_flag

    #         if "recipient" in msg_content:
    #             recipient = msg_content["recipient"]  # type: ignore
    #             recipient_agent, recipient_swarm = parse_agent_address(
    #                 recipient["address"]
    #             )

    #             # If recipient is in a different swarm, route via HTTP
    #             if recipient_swarm and recipient_swarm != self.local_swarm_name:
    #                 response = await self._route_to_remote_swarm(
    #                     message,
    #                     recipient_swarm,
    #                     stream_requested=stream_requested,
    #                     stream_handler=stream_handler,
    #                     ignore_stream_pings=ignore_pings,
    #                     is_response=message["msg_type"] == "response",
    #                 )
    #             else:
    #                 # Local message, handle normally
    #                 response = await self._route_to_local_agent(message)

    #             return response

    #         # Check if recipients list contains interswarm addresses
    #         elif "recipients" in msg_content:
    #             recipients = msg_content["recipients"]
    #             local_recipients = []
    #             remote_routes: dict[str, list[str]] = {}

    #             for recipient in recipients:
    #                 recipient_agent, recipient_swarm = parse_agent_address(
    #                     recipient["address"]
    #                 )

    #                 if recipient_swarm and recipient_swarm != self.local_swarm_name:
    #                     # Remote recipient
    #                     if recipient_swarm not in remote_routes:
    #                         remote_routes[recipient_swarm] = []
    #                     remote_routes[recipient_swarm].append(recipient_agent)
    #                 else:
    #                     # Local recipient
    #                     local_recipients.append(recipient_agent)

    #             # Route to local recipients
    #             if local_recipients:
    #                 local_message = self._create_local_message(
    #                     message, local_recipients
    #                 )
    #                 response = await self._route_to_local_agent(local_message)

    #             # Route to remote swarms
    #             for swarm_name, agents in remote_routes.items():
    #                 remote_message = self._create_remote_message(
    #                     message, agents, swarm_name
    #                 )
    #                 response = await self._route_to_remote_swarm(
    #                     remote_message,
    #                     swarm_name,
    #                     stream_requested=stream_requested,
    #                     stream_handler=stream_handler,
    #                     ignore_stream_pings=ignore_pings,
    #                     is_response=remote_message["msg_type"] == "response",
    #                 )

    #             return response

    #         else:
    #             # No recipients found
    #             logger.error(
    #                 f"{self._log_prelude()} message '{message['id']}' has no recipients"
    #             )
    #             return self._system_router_message(message, "message has no recipients")

    #     except Exception as e:
    #         logger.error(
    #             f"{self._log_prelude()} error routing message '{message['id']}': '{e}'"
    #         )
    #         return self._system_router_message(message, f"error routing message: '{e}'")

    # async def _route_to_local_agent(self, message: MAILInterswarmMessage) -> MAILMessage:
    #     """
    #     Route a message to a local agent.
    #     """
    #     try:
    #         # This will be handled by the local MAIL system
    #         # We need to register a handler that the core MAIL can call
    #         if "local_message_handler" in self.message_handlers:
    #             await self.message_handlers["local_message_handler"](message)
    #             return message
    #         else:
    #             logger.warning(
    #                 f"{self._log_prelude()} no local message handler registered"
    #             )
    #             return self._system_router_message(
    #                 message, "no local message handler registered"
    #             )
    #     except Exception as e:
    #         logger.error(
    #             f"{self._log_prelude()} error routing message '{message['id']}' to local agent: '{e}'"
    #         )
    #         return self._system_router_message(
    #             message, f"error routing to local agent: '{e}'"
    #         )

    # async def _route_to_remote_swarm(
    #     self,
    #     message: MAILMessage,
    #     swarm_name: str,
    #     *,
    #     stream_requested: bool = False,
    #     stream_handler: StreamHandler | None = None,
    #     ignore_stream_pings: bool = False,
    #     is_response: bool = False,
    # ) -> MAILMessage:
    #     """
    #     Route a message to a remote swarm via HTTP.
    #     """
    #     try:
    #         endpoint = self.swarm_registry.get_swarm_endpoint(swarm_name)
    #         if not endpoint:
    #             logger.error(
    #                 f"{self._log_prelude()} unknown swarm endpoint: '{swarm_name}'"
    #             )
    #             return self._system_router_message(
    #                 message, f"unknown swarm endpoint: '{swarm_name}'"
    #             )

    #         if not endpoint["is_active"]:
    #             logger.warning(
    #                 f"{self._log_prelude()} swarm '{swarm_name}' is not active"
    #             )
    #             return self._system_router_message(
    #                 message, f"swarm '{swarm_name}' is not active"
    #             )

    #         msg_content = message["message"]

    #         # Normalise sender metadata so the remote swarm knows who called.
    #         current_sender = msg_content.get("sender", {})
    #         if isinstance(current_sender, dict):
    #             sender_address = current_sender.get("address")
    #             sender_agent, sender_swarm = (
    #                 parse_agent_address(sender_address)
    #                 if sender_address
    #                 else (None, None)
    #             )
    #             if sender_agent:
    #                 if sender_swarm != self.local_swarm_name:
    #                     msg_content["sender"] = format_agent_address(
    #                         sender_agent, self.local_swarm_name
    #                     )
    #             else:
    #                 fallback_agent = (
    #                     sender_address
    #                     if isinstance(sender_address, str) and sender_address
    #                     else current_sender
    #                     if isinstance(current_sender, str) and current_sender
    #                     else "unknown"
    #                 )
    #                 msg_content["sender"] = format_agent_address(
    #                     fallback_agent, self.local_swarm_name
    #                 )
    #         else:
    #             fallback_agent = (
    #                 current_sender if isinstance(current_sender, str) else "unknown"
    #             )
    #             msg_content["sender"] = format_agent_address(
    #                 fallback_agent, self.local_swarm_name
    #             )

    #         # Ensure interswarm metadata is populated so the receiver can detect the
    #         # remote origin and complete tasks without a ping-pong acknowledgement loop.
    #         msg_content["sender_swarm"] = self.local_swarm_name
    #         if "recipient" in msg_content:
    #             msg_content["recipient_swarm"] = swarm_name  # type: ignore
    #         elif "recipients" in msg_content:
    #             existing_swarms = cast(
    #                 list[str] | None, msg_content.get("recipient_swarms")
    #             )
    #             if existing_swarms is not None:
    #                 if swarm_name not in existing_swarms:
    #                     existing_swarms.append(swarm_name)
    #             else:
    #                 msg_content["recipient_swarms"] = [swarm_name]  # type: ignore[index]

    #         auth_token = self.swarm_registry.get_resolved_auth_token(swarm_name)
    #         if not auth_token:
    #             logger.error(
    #                 f"{self._log_prelude()} no auth token configured for swarm '{swarm_name}'"
    #             )
    #             return self._system_router_message(
    #                 message,
    #                 f"auth token for swarm '{swarm_name}' is not configured; cannot send interswarm message",
    #             )

    #         headers = {
    #             "Content-Type": "application/json",
    #             "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
    #             "Authorization": f"Bearer {auth_token}",
    #         }

    #         timeout = aiohttp.ClientTimeout(total=3600)
    #         assert self.session is not None
    #         if is_response:
    #             url = f"{endpoint['base_url']}/interswarm/response"
    #             headers["Accept"] = "application/json"

    #             async with self.session.post(
    #                 url, json=message, headers=headers, timeout=timeout
    #             ) as response:
    #                 raw_body = await response.text()
    #                 payload: Any | None = None
    #                 if raw_body:
    #                     try:
    #                         payload = json.loads(raw_body)
    #                     except json.JSONDecodeError:
    #                         payload = None

    #                 if response.status == 200:
    #                     status = (
    #                         payload.get("status")
    #                         if isinstance(payload, dict)
    #                         else None
    #                     )
    #                     if status and status != "response_processed":
    #                         detail = (
    #                             payload.get("detail")
    #                             if isinstance(payload, dict)
    #                             else None
    #                         )
    #                         reason = (
    #                             f"{detail} (status={status})"
    #                             if detail
    #                             else f"remote swarm '{swarm_name}' returned status '{status}'"
    #                         )
    #                         logger.warning(
    #                             f"{self._log_prelude()} swarm '{swarm_name}' did not process response: '{status}'"
    #                         )
    #                         return self._system_router_message(message, reason)

    #                     logger.info(
    #                         f"{self._log_prelude()} delivered interswarm response '{message['id']}' to swarm '{swarm_name}'"
    #                     )
    #                     return message

    #                 detail_message = None
    #                 if isinstance(payload, dict):
    #                     detail_message = payload.get("detail")
    #                 if not detail_message:
    #                     detail_message = raw_body or response.reason

    #                 logger.error(
    #                     f"{self._log_prelude()} failed to deliver interswarm response '{message['id']}' to swarm '{swarm_name}'"
    #                 )
    #                 return self._system_router_message(
    #                     message,
    #                     f"failed to deliver response to swarm '{swarm_name}': {detail_message}",
    #                 )

    #         # Create interswarm message wrapper for non-response payloads
    #         metadata: dict[str, Any] = {
    #             "original_message_id": message["id"],
    #             "routing_info": message["message"].get("routing_info", {}),
    #             "expect_response": True,
    #         }
    #         if stream_requested:
    #             metadata["stream"] = True
    #             if ignore_stream_pings:
    #                 metadata["ignore_stream_pings"] = True

    #         interswarm_message = MAILInterswarmMessage(
    #             message_id=str(uuid.uuid4()),
    #             source_swarm=self.local_swarm_name,
    #             target_swarm=swarm_name,
    #             timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
    #             payload=message["message"],
    #             msg_type=message["msg_type"],  # type: ignore
    #             auth_token=auth_token,
    #             metadata=metadata,
    #         )

    #         url = f"{endpoint['base_url']}/interswarm/message"
    #         if stream_requested:
    #             headers["Accept"] = "text/event-stream"

    #         async with self.session.post(
    #             url, json=interswarm_message, headers=headers, timeout=timeout
    #         ) as response:
    #             content_type = response.headers.get("Content-Type", "")
    #             if (
    #                 stream_requested
    #                 and response.status == 200
    #                 and "text/event-stream" in content_type
    #             ):
    #                 final_message = await self._consume_stream(
    #                     response,
    #                     message,
    #                     swarm_name,
    #                     stream_handler=stream_handler,
    #                     ignore_stream_pings=ignore_stream_pings,
    #                 )
    #                 await response.release()
    #                 return final_message

    #             if response.status == 200:
    #                 logger.info(
    #                     f"{self._log_prelude()} successfully routed message '{message['id']}' to swarm: '{swarm_name}'"
    #                 )
    #                 response_json = await response.json()
    #                 return MAILMessage(**response_json)  # type: ignore

    #             logger.error(
    #                 f"{self._log_prelude()} failed to route message '{message['id']}' to swarm '{swarm_name}' with status: '{response.status}'"
    #             )
    #             return self._system_router_message(
    #                 message,
    #                 f"failed to route message to swarm '{swarm_name}' with status: '{response.status}'",
    #             )

    #     except Exception as e:
    #         logger.error(
    #             f"{self._log_prelude()} error routing message '{message['id']}' to remote swarm '{swarm_name}' with error: '{e}'"
    #         )
    #         return self._system_router_message(
    #             message,
    #             f"error routing message '{message['id']}' to remote swarm '{swarm_name}' with error: '{e}'",
    #         )

    # async def handle_incoming_response(self, response_message: MAILMessage) -> bool:
    #     """
    #     Handle an incoming response from a remote swarm.
    #     """
    #     try:
    #         # Route the response to the local MAIL instance
    #         if "local_message_handler" in self.message_handlers:
    #             await self.message_handlers["local_message_handler"](response_message)
    #             logger.info(
    #                 f"{self._log_prelude()} successfully handled incoming response from remote swarm"
    #             )
    #             return True
    #         else:
    #             logger.warning(
    #                 f"{self._log_prelude()} no local message handler registered for incoming responses"
    #             )
    #             return False

    #     except Exception as e:
    #         logger.error(
    #             f"{self._log_prelude()} error handling incoming response '{response_message['id']}': '{e}'"
    #         )
    #         return False

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

    async def _consume_stream(
        self,
        response: aiohttp.ClientResponse,
        original_message: MAILMessage,
        swarm_name: str,
        *,
        stream_handler: StreamHandler | None = None,
        ignore_stream_pings: bool = False,
    ) -> MAILMessage:
        """
        Consume an SSE response from a remote swarm and return the final MAILMessage.
        """

        final_message: MAILMessage | None = None
        task_failed = False
        failure_reason: str | None = None

        async for event_name, payload in self._iter_sse(response):
            if event_name == "ping" and ignore_stream_pings:
                continue

            if stream_handler is not None:
                await stream_handler(event_name, payload)

            if event_name == "new_message" and payload:
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    logger.debug(
                        f"{self._log_prelude()} unable to parse streaming 'new_message' payload from swarm '{swarm_name}'"
                    )
                    continue

                message_data = (
                    data.get("extra_data", {}).get("full_message")
                    if isinstance(data, dict)
                    else None
                )

                if isinstance(message_data, dict):
                    try:
                        candidate = cast(MAILMessage, message_data)
                    except TypeError:
                        logger.debug(
                            f"{self._log_prelude()} received non-conforming message in stream from '{swarm_name}'"
                        )
                        continue

                    task_id = (
                        candidate["message"].get("task_id")
                        if isinstance(candidate.get("message"), dict)
                        else None
                    )
                    original_task_id = (
                        original_message["message"].get("task_id")
                        if isinstance(original_message.get("message"), dict)
                        else None
                    )
                    if task_id and task_id == original_task_id:
                        final_message = candidate

            elif event_name == "task_error":
                task_failed = True
                if payload:
                    try:
                        data = json.loads(payload)
                        failure_reason = (
                            data.get("response") if isinstance(data, dict) else None
                        )
                    except json.JSONDecodeError:
                        failure_reason = payload
                break
            elif event_name == "task_complete":
                break

        if final_message is not None:
            return final_message

        if task_failed:
            reason = failure_reason or "remote task reported an error"
            return self._system_router_message(original_message, reason)

        logger.error(
            f"{self._log_prelude()} streamed interswarm response from '{swarm_name}' ended without delivering a final message",
        )
        return self._system_router_message(
            original_message,
            "stream ended before a final response was received",
        )

    async def _iter_sse(
        self, response: aiohttp.ClientResponse
    ) -> AsyncIterator[tuple[str, str | None]]:
        """
        Yield (event, data) tuples from an SSE response.
        """

        event_name = "message"
        data_lines: list[str] = []

        async for raw_line in response.content:
            line = raw_line.decode("utf-8", errors="ignore").rstrip("\n")
            if line.endswith("\r"):
                line = line[:-1]

            if line == "":
                if data_lines or event_name != "message":
                    data = "\n".join(data_lines) if data_lines else None
                    yield event_name, data
                event_name = "message"
                data_lines = []
                continue

            if line.startswith(":"):
                continue

            if line.startswith("event:"):
                event_name = line[len("event:") :].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())

        if data_lines or event_name != "message":
            data = "\n".join(data_lines) if data_lines else None
            yield event_name, data

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

    # async def handle_incoming_interswarm_message(
    #     self, interswarm_message: MAILInterswarmMessage
    # ) -> bool:
    #     """
    #     Handle an incoming interswarm message from a remote swarm.
    #     """
    #     try:
    #         # Validate the message
    #         if interswarm_message["target_swarm"] != self.local_swarm_name:
    #             logger.error(
    #                 f"{self._log_prelude()} received message intended for '{interswarm_message['target_swarm']}'"
    #             )
    #             return False

    #         # Extract the original MAIL message
    #         original_message = MAILMessage(
    #             id=interswarm_message["message_id"],
    #             timestamp=interswarm_message["timestamp"],
    #             message=interswarm_message["payload"],
    #             msg_type=self._determine_message_type(interswarm_message["payload"]),  # type: ignore
    #         )

    #         # Route to local handler
    #         if "local_message_handler" in self.message_handlers:
    #             await self.message_handlers["local_message_handler"](original_message)
    #             logger.info(
    #                 f"{self._log_prelude()} successfully handled incoming interswarm message '{interswarm_message['message_id']}' from '{interswarm_message['source_swarm']}'"
    #             )
    #             return True
    #         else:
    #             logger.warning(
    #                 f"{self._log_prelude()} no local message handler registered for incoming interswarm messages"
    #             )
    #             return False

    #     except Exception as e:
    #         logger.error(
    #             f"{self._log_prelude()} error handling incoming interswarm message '{interswarm_message['message_id']}': '{e}'"
    #         )
    #         return False

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

    # async def broadcast_to_all_swarms(self, message: MAILMessage) -> dict[str, bool]:
    #     """
    #     Broadcast a message to all known swarms.
    #     """
    #     results: dict[str, bool] = {}
    #     active_endpoints = self.swarm_registry.get_active_endpoints()

    #     for swarm_name, endpoint in active_endpoints.items():
    #         if swarm_name != self.local_swarm_name:
    #             response = await self._route_to_remote_swarm(message, swarm_name)
    #             results[swarm_name] = response is not None

    #     return results

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
        match message["msg_type"]:
            case "request":
                request_id = message["message"]["request_id"]  # type: ignore
            case "response":
                request_id = message["message"]["request_id"]  # type: ignore
            case "broadcast":
                request_id = message["message"]["broadcast_id"]  # type: ignore
            case "interrupt":
                request_id = message["message"]["interrupt_id"]  # type: ignore
            case _:
                raise ValueError(f"invalid message type: {message['msg_type']}")
        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILResponse(
                task_id=message["message"]["task_id"],
                request_id=request_id,
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
