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
        self.message_handlers: dict[
            str, Callable[[MAILInterswarmMessage], Awaitable[None]]
        ] = {}

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
        self,
        message_type: str,
        handler: Callable[[MAILInterswarmMessage], Awaitable[None]],
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
            logger.error(
                f"{self._log_prelude()} received interswarm message for wrong swarm: '{message['target_swarm']}'"
            )
            raise ValueError(
                f"received interswarm message for wrong swarm: '{message['target_swarm']}'"
            )

        # attempt to post this message to the local swarm
        try:
            handler = self.message_handlers.get("local_message_handler")
            if handler:
                await handler(message)
            else:
                logger.warning(
                    f"{self._log_prelude()} no local message handler registered"
                )
                raise ValueError("no local message handler registered")
        except Exception as e:
            logger.error(
                f"{self._log_prelude()} router failed to receive interswarm message forward: {e}"
            )
            raise ValueError(
                f"router failed to receive interswarm message forward: {e}"
            )

    async def receive_interswarm_message_back(
        self,
        message: MAILInterswarmMessage,
    ) -> None:
        """
        Receive an interswarm message in the case of a task resolution.
        """
        # ensure this is the right target swarm
        if message["target_swarm"] != self.local_swarm_name:
            logger.error(
                f"{self._log_prelude()} received interswarm message for wrong swarm: '{message['target_swarm']}'"
            )
            raise ValueError(
                f"received interswarm message for wrong swarm: '{message['target_swarm']}'"
            )

        # attempt to post this message to the local swarm
        try:
            handler = self.message_handlers.get("local_message_handler")
            if handler:
                await handler(message)
            else:
                logger.warning(
                    f"{self._log_prelude()} no local message handler registered"
                )
                raise ValueError("no local message handler registered")
        except Exception as e:
            logger.error(
                f"{self._log_prelude()} router failed to receive interswarm message back: {e}"
            )
            raise ValueError(f"router failed to receive interswarm message back: {e}")

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
            logger.error(
                f"{self._log_prelude()} unknown swarm endpoint: '{message['target_swarm']}'"
            )
            raise ValueError(f"unknown swarm endpoint: '{message['target_swarm']}'")

        # ensure the target swarm is active
        if not endpoint["is_active"]:
            logger.error(
                f"{self._log_prelude()} swarm '{message['target_swarm']}' is not active"
            )
            raise ValueError(f"swarm '{message['target_swarm']}' is not active")

        # ensure this session is open
        if self.session is None:
            logger.error(f"{self._log_prelude()} HTTP client session is not open")
            raise ValueError("HTTP client session is not open")

        # attempt to send this message to the remote swarm
        try:
            token = self._resolve_auth_token_ref(endpoint.get("swarm_name"))
            if not token:
                token = message.get("auth_token")
            if not token:
                raise ValueError(
                    f"authentication token missing for swarm '{message['target_swarm']}'"
                )
            async with self.session.post(
                endpoint["base_url"] + "/interswarm/forward",
                json={
                    "message": self._prep_message_for_interswarm(message),
                },
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"{self._log_prelude()} router failed to send interswarm message forward to swarm '{message['target_swarm']}': {response.status}"
                    )
                    raise ValueError(
                        f"router failed to send interswarm message forward to swarm '{message['target_swarm']}': HTTP status code {response.status}, reason '{response.reason}'"
                    )
                else:
                    logger.info(
                        f"{self._log_prelude()} router successfully sent interswarm message forward to swarm '{message['target_swarm']}'"
                    )
                    return
        except Exception as e:
            logger.error(
                f"{self._log_prelude()} router failed to send interswarm message forward: {e}"
            )
            raise ValueError(f"router failed to send interswarm message forward: {e}")

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
            logger.error(
                f"{self._log_prelude()} unknown swarm endpoint: '{message['target_swarm']}'"
            )
            raise ValueError(f"unknown swarm endpoint: '{message['target_swarm']}'")

        # ensure the target swarm is active
        if not endpoint["is_active"]:
            logger.error(
                f"{self._log_prelude()} swarm '{message['target_swarm']}' is not active"
            )
            raise ValueError(f"swarm '{message['target_swarm']}' is not active")

        # ensure this session is open
        if self.session is None:
            logger.error(f"{self._log_prelude()} HTTP client session is not open")
            raise ValueError("HTTP client session is not open")

        # attempt to send this message to the remote swarm
        try:
            token = self._resolve_auth_token_ref(endpoint.get("swarm_name"))
            if not token:
                token = message.get("auth_token")
            if not token:
                raise ValueError(
                    f"authentication token missing for swarm '{message['target_swarm']}'"
                )
            async with self.session.post(
                endpoint["base_url"] + "/interswarm/back",
                json={
                    "message": self._prep_message_for_interswarm(message),
                },
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"{self._log_prelude()} router failed to send interswarm message back to swarm '{message['target_swarm']}': {response.status}"
                    )
                    raise ValueError(
                        f"router failed to send interswarm message back to swarm '{message['target_swarm']}': HTTP status code {response.status}, reason '{response.reason}'"
                    )
                else:
                    logger.info(
                        f"{self._log_prelude()} successfully sent interswarm message back to swarm '{message['target_swarm']}'"
                    )
                    return
        except Exception as e:
            logger.error(
                f"{self._log_prelude()} router failed to send interswarm message back: {e}"
            )
            raise ValueError(f"router failed to send interswarm message back: {e}")

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
            logger.error(
                f"{self._log_prelude()} unknown swarm endpoint: '{message['target_swarm']}'"
            )
            raise ValueError(f"unknown swarm endpoint: '{message['target_swarm']}'")

        # ensure the target swarm is active
        if not endpoint["is_active"]:
            logger.error(
                f"{self._log_prelude()} swarm '{message['target_swarm']}' is not active"
            )
            raise ValueError(f"swarm '{message['target_swarm']}' is not active")

        # ensure this session is open
        if self.session is None:
            logger.error(f"{self._log_prelude()} HTTP client session is not open")
            raise ValueError("HTTP client session is not open")

        # attempt to post this message to the remote swarm
        try:
            auth_token = message.get("auth_token")
            if not auth_token:
                raise ValueError("user token is required for interswarm user messages")

            payload = message.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError("invalid interswarm payload")

            msg_type = message.get("msg_type")
            if msg_type not in {"request", "broadcast"}:
                raise ValueError(
                    f"msg_type '{msg_type}' is not supported for interswarm user messages"
                )

            subject = payload.get("subject") if isinstance(payload.get("subject"), str) else None
            body = payload.get("body") if isinstance(payload.get("body"), str) else None
            task_id = payload.get("task_id") if isinstance(payload.get("task_id"), str) else None
            routing_info = payload.get("routing_info") if isinstance(payload.get("routing_info"), dict) else {}

            if body is None:
                raise ValueError("body is required for interswarm user messages")

            targets: list[str] = []
            if msg_type == "request":
                recipient = payload.get("recipient")
                if isinstance(recipient, dict):
                    address = recipient.get("address")
                    if isinstance(address, str):
                        targets = [address]
            elif msg_type == "broadcast":
                recipients = payload.get("recipients")
                if isinstance(recipients, list):
                    for recipient in recipients:
                        if isinstance(recipient, dict):
                            address = recipient.get("address")
                            if isinstance(address, str):
                                targets.append(address)

            if not targets:
                raise ValueError("targets are required for interswarm user messages")

            request_body: dict[str, Any] = {
                "user_token": auth_token,
                "body": body,
                "targets": targets,
                "msg_type": msg_type,
            }
            if subject is not None:
                request_body["subject"] = subject
            if task_id is not None:
                request_body["task_id"] = task_id
            if routing_info:
                request_body["routing_info"] = routing_info
            if "stream" in routing_info:
                request_body["stream"] = bool(routing_info.get("stream"))
            if "ignore_stream_pings" in routing_info:
                request_body["ignore_stream_pings"] = bool(
                    routing_info.get("ignore_stream_pings")
                )

            async with self.session.post(
                endpoint["base_url"] + "/interswarm/message",
                json=request_body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"MAIL-Interswarm-Router/{self.local_swarm_name}",
                    "Authorization": f"Bearer {auth_token}",
                },
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"{self._log_prelude()} failed to post interswarm user message to swarm '{message['target_swarm']}': '{response.status}'"
                    )
                    raise ValueError(
                        f"failed to post interswarm user message to swarm '{message['target_swarm']}': HTTP status code '{response.status}', reason '{response.reason}'"
                    )
                else:
                    logger.info(
                        f"{self._log_prelude()} successfully posted interswarm user message to swarm '{message['target_swarm']}'"
                    )
                    return cast(MAILMessage, await response.json())
        except Exception as e:
            logger.error(
                f"{self._log_prelude()} error posting interswarm user message: {e}"
            )
            raise ValueError(f"error posting interswarm user message: {e}")

    def _prep_message_for_interswarm(
        self, message: MAILInterswarmMessage
    ) -> MAILInterswarmMessage:
        """
        Ensure the sender follows the interswarm address format (agent@swarm).
        """
        payload = message["payload"]
        sender_agent, sender_swarm = parse_agent_address(payload["sender"]["address"])
        if sender_swarm != self.local_swarm_name:
            payload["sender"] = format_agent_address(
                sender_agent, self.local_swarm_name
            )

        return MAILInterswarmMessage(
            message_id=message["message_id"],
            source_swarm=message["source_swarm"],
            target_swarm=message["target_swarm"],
            timestamp=message["timestamp"],
            payload=payload,
            msg_type=message["msg_type"],
            auth_token=message["auth_token"],
            task_owner=message["task_owner"],
            task_contributors=message["task_contributors"],
            metadata=message["metadata"],
        )

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
        all_targets = self._get_target_swarms(message)
        target_swarm = all_targets[0]
        return MAILInterswarmMessage(
            message_id=message["id"],
            source_swarm=self.local_swarm_name,
            target_swarm=target_swarm,
            timestamp=message["timestamp"],
            payload=message["message"],
            msg_type=message["msg_type"],  # type: ignore
            auth_token=self.swarm_registry.get_resolved_auth_token(target_swarm),
            task_owner=task_owner,
            task_contributors=task_contributors,
            metadata=metadata or {},
        )

    def _get_target_swarms(self, message: MAILMessage) -> list[str]:
        """
        Build the list of target swarms for a message.
        """
        targets = message["message"].get("recipients") or [
            message["message"].get("recipient")
        ]
        assert isinstance(targets, list)
        return [
            cast(str, parse_agent_address(target["address"])[1])
            for target in targets
            if parse_agent_address(target["address"])[1] is not None
        ]

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
