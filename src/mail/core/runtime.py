# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import datetime
import logging
import uuid
from asyncio import PriorityQueue, Task
from collections.abc import AsyncGenerator
from typing import Any

from langmem import create_memory_store_manager
from sse_starlette import ServerSentEvent

from mail.factories import (
    ActionFunction,
    ActionOverrideFunction,
    AgentFunction,
)
from mail.net import InterswarmRouter, SwarmRegistry
from mail.utils.store import get_langmem_store

from .executor import execute_action_tool
from .message import (
    MAILAddress,
    MAILBroadcast,
    MAILMessage,
    MAILResponse,
    build_mail_xml,
    create_agent_address,
    create_system_address,
    parse_agent_address,
)
from .tools import (
    MAIL_TOOL_NAMES,
    convert_call_to_mail_message,
)

logger = logging.getLogger("mail.runtime")


class MAILRuntime:
    """
    Runtime for an individual MAIL swarm instance.
    Handles the local message queue and provides an action executor for tools.
    """

    def __init__(
        self,
        agents: dict[str, AgentFunction],
        actions: dict[str, ActionFunction],
        user_id: str,
        swarm_name: str = "example",
        swarm_registry: SwarmRegistry | None = None,
        enable_interswarm: bool = False,
        entrypoint: str = "supervisor",
    ):
        # Use a priority queue with a deterministic tiebreaker to avoid comparing dicts
        # Structure: (priority, seq, message)
        self.message_queue: PriorityQueue[tuple[int, int, MAILMessage]] = (
            PriorityQueue()
        )
        self._message_seq: int = 0
        self.response_queue: asyncio.Queue[tuple[str, MAILMessage]] = asyncio.Queue()
        self.agents = agents
        self.actions = actions
        self.agent_histories: dict[str, list[dict[str, Any]]] = {
            agent: [] for agent in agents
        }
        self.active_tasks: set[Task[Any]] = set()
        self.shutdown_event = asyncio.Event()
        self.response_to_user: MAILMessage | None = None
        self.is_running = False
        self.current_request_id: str | None = None
        self.pending_requests: dict[str, asyncio.Future[MAILMessage]] = {}
        self.user_id = user_id
        self.events: list[ServerSentEvent] = []
        self.new_events: list[ServerSentEvent] = []
        # Event notifier for streaming to avoid busy-waiting
        self._events_available = asyncio.Event()
        # Interswarm messaging support
        self.swarm_name = swarm_name
        self.enable_interswarm = enable_interswarm
        self.swarm_registry = swarm_registry
        self.interswarm_router: InterswarmRouter | None = None
        self.entrypoint = entrypoint
        if enable_interswarm and swarm_registry:
            self.interswarm_router = InterswarmRouter(swarm_registry, swarm_name)
            # Register local message handler
            self.interswarm_router.register_message_handler(
                "local_message_handler", self._handle_local_message
            )

    async def start_interswarm(self) -> None:
        """
        Start interswarm messaging capabilities.
        """
        if self.enable_interswarm and self.interswarm_router:
            await self.interswarm_router.start()
            logger.info(f"started interswarm messaging for swarm: '{self.swarm_name}'")

    async def stop_interswarm(self) -> None:
        """
        Stop interswarm messaging capabilities.
        """
        if self.interswarm_router:
            await self.interswarm_router.stop()
            logger.info(f"stopped interswarm messaging for swarm: '{self.swarm_name}'")

    async def is_interswarm_running(self) -> bool:
        """
        Check if interswarm messaging is running.
        """
        if self.interswarm_router:
            return await self.interswarm_router.is_running()
        return False

    async def _handle_local_message(self, message: MAILMessage) -> None:
        """
        Handle a message that should be processed locally.
        """
        await self.submit(message)

    async def handle_interswarm_response(self, response_message: MAILMessage) -> None:
        """
        Handle an incoming response from a remote swarm.
        """
        logger.info(f"handling interswarm response: '{response_message['id']}'")

        # Submit the response to the local message queue for processing
        # This will allow the local supervisor agent to process the response
        # and generate a final response for the user
        await self.submit(response_message)

        # Don't immediately complete the pending request here
        # Let the local processing flow handle it naturally
        # The supervisor agent should process the response and generate
        # a final response that will complete the user's request

    async def run(
        self, _action_override: ActionOverrideFunction | None = None
    ) -> MAILMessage:
        """
        Run the MAIL system until a task is complete or shutdown is requested.
        This method can be called multiple times for different requests.
        """
        if self.is_running:
            logger.warning(
                f"MAIL is already running for user '{self.user_id}', cannot start another run"
            )
            return self._system_broadcast(
                task_id="null",
                subject="Runtime Error",
                body="MAIL is already running, cannot start another run",
                task_complete=True,
            )

        self.is_running = True

        try:
            while True:
                try:
                    # Wait for either a message or shutdown signal
                    get_message_task = asyncio.create_task(self.message_queue.get())
                    shutdown_task = asyncio.create_task(self.shutdown_event.wait())

                    done, pending = await asyncio.wait(
                        [get_message_task, shutdown_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    # Check if shutdown was requested
                    if shutdown_task in done:
                        logger.info(f"shutdown requested for user '{self.user_id}'...")
                        return self._system_broadcast(
                            task_id="null",
                            subject="Shutdown Requested",
                            body="The shutdown was requested.",
                            task_complete=True,
                        )

                    # Process the message
                    message_tuple = get_message_task.result()
                    # message_tuple structure: (priority, seq, message)
                    message = message_tuple[2]
                    logger.info(
                        f"processing message for user '{self.user_id}' with message: '{message}'"
                    )

                    if message["msg_type"] == "broadcast_complete":
                        # Mark this message as done before breaking
                        self.message_queue.task_done()
                        return message

                    await self._process_message(message, _action_override)
                    # Note: task_done() is called by the schedule function for regular messages

                except asyncio.CancelledError:
                    logger.info(
                        f"run loop cancelled for user '{self.user_id}', initiating shutdown..."
                    )
                    self._submit_event(
                        "run_loop_cancelled",
                        message["message"]["task_id"],
                        f"run loop for user '{self.user_id}' cancelled",
                    )
                    return self._system_broadcast(
                        task_id=message["message"]["task_id"],
                        subject="Run Loop Cancelled",
                        body="The run loop was cancelled.",
                        task_complete=True,
                    )
                except Exception as e:
                    logger.error(
                        f"error in run loop for user '{self.user_id}' with error: '{e}'"
                    )
                    self._submit_event(
                        "run_loop_error",
                        message["message"]["task_id"],
                        f"error in run loop for user '{self.user_id}' with error: '{e}'",
                    )
                    return self._system_broadcast(
                        task_id=message["message"]["task_id"],
                        subject="Error in run loop",
                        body=f"An error occurred while running the MAIL system: '{e}'",
                        task_complete=True,
                    )
        finally:
            self.is_running = False

    async def run_continuous(
        self, _action_override: ActionOverrideFunction | None = None
    ) -> None:
        """
        Run the MAIL system continuously, handling multiple requests.
        This method runs indefinitely until shutdown is requested.
        """
        logger.info(f"starting continuous MAIL operation for user '{self.user_id}'...")

        while not self.shutdown_event.is_set():
            try:
                logger.debug(f"pending requests: {self.pending_requests}")

                # Wait for either a message or shutdown signal
                get_message_task = asyncio.create_task(self.message_queue.get())
                shutdown_task = asyncio.create_task(self.shutdown_event.wait())

                done, pending = await asyncio.wait(
                    [get_message_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if shutdown was requested
                if shutdown_task in done:
                    logger.info(
                        f"shutdown requested in continuous mode for user '{self.user_id}'..."
                    )
                    self._submit_event(
                        "shutdown_requested",
                        f"* for user '{self.user_id}'",
                        "shutdown requested in continuous mode",
                    )
                    break

                # Process the message
                message_tuple = get_message_task.result()
                # message_tuple structure: (priority, seq, message)
                message = message_tuple[2]
                logger.info(
                    f"processing message in continuous mode for user '{self.user_id}' with message: '{message}'"
                )

                if message["msg_type"] == "broadcast_complete":
                    # Check if this completes a pending request
                    msg_content = message["message"]
                    if (
                        "task_id" in msg_content
                        and msg_content["task_id"] in self.pending_requests
                    ):
                        # Resolve the pending request
                        logger.info(
                            f"task '{msg_content['task_id']}' completed, resolving pending request"
                        )
                        future = self.pending_requests.pop(msg_content["task_id"])
                        if not future.done():
                            future.set_result(message)
                    else:
                        # Mark this message as done and continue processing
                        self.message_queue.task_done()
                        continue

                await self._process_message(message, _action_override)
                # Note: task_done() is called by the schedule function for regular messages

            except asyncio.CancelledError:
                logger.info(
                    f"continuous run loop cancelled for user '{self.user_id}'..."
                )
                self._submit_event(
                    "run_loop_cancelled",
                    f"* for user '{self.user_id}'",
                    "continuous run loop cancelled",
                )
                break
            except Exception as e:
                logger.error(
                    f"error in continuous run loop for user '{self.user_id}' with error: '{e}'"
                )
                self._submit_event(
                    "run_loop_error",
                    f"* for user '{self.user_id}'",
                    f"continuous run loop error: '{e}'",
                )
                # Continue processing other messages instead of shutting down
                continue

        logger.info(f"continuous MAIL operation stopped for user '{self.user_id}'.")

    async def submit_and_wait(
        self, message: MAILMessage, timeout: float = 3600.0
    ) -> MAILMessage:
        """
        Submit a message and wait for the response.
        This method is designed for handling individual task requests in a persistent MAIL instance.
        """
        task_id = message["message"]["task_id"]

        logger.info(
            f"'submit_and_wait': creating future for task '{task_id}' for user '{self.user_id}'"
        )

        # Create a future to wait for the response
        future: asyncio.Future[MAILMessage] = asyncio.Future()
        self.pending_requests[task_id] = future

        try:
            # Submit the message
            logger.info(f"'submit_and_wait': submitting message for task '{task_id}'")
            await self.submit(message)

            # Wait for the response with timeout
            logger.info(f"'submit_and_wait': waiting for future for task '{task_id}'")
            response = await asyncio.wait_for(future, timeout=timeout)
            logger.info(
                f"'submit_and_wait': got response for task '{task_id}' with body: '{response['message']['body'][:50]}...'..."
            )
            self._submit_event(
                "task_complete", task_id, f"response: '{response['message']['body']}'"
            )
            return response

        except TimeoutError:
            # Remove the pending request
            self.pending_requests.pop(task_id, None)
            logger.error(f"'submit_and_wait': timeout for task '{task_id}'")
            self._submit_event("task_error", task_id, f"timeout for task '{task_id}'")
            return self._system_broadcast(
                task_id=task_id,
                subject="Task Timeout",
                body="The task timed out.",
                task_complete=True,
            )
        except Exception as e:
            # Remove the pending request
            self.pending_requests.pop(task_id, None)
            logger.error(
                f"'submit_and_wait': exception for task '{task_id}' with error: '{e}'"
            )
            self._submit_event("task_error", task_id, f"error for task: '{e}'")
            return self._system_broadcast(
                task_id=task_id,
                subject="Task Error",
                body=f"The task encountered an error: '{e}'.",
                task_complete=True,
            )

    async def submit_and_stream(
        self, message: MAILMessage, timeout: float = 3600.0
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """
        Submit a message and stream the response.
        This method is designed for handling individual task requests in a persistent MAIL instance.
        """
        task_id = message["message"]["task_id"]

        logger.info(
            f"'submit_and_stream': creating future for task '{task_id}' for user '{self.user_id}'"
        )

        future: asyncio.Future[MAILMessage] = asyncio.Future()
        self.pending_requests[task_id] = future

        try:
            # Submit the message for processing
            await self.submit(message)

            # Stream events as they become available, emitting periodic heartbeats
            while not future.done():
                try:
                    # Wait up to 15s for new events; on timeout send a heartbeat
                    await asyncio.wait_for(self._events_available.wait(), timeout=15.0)
                except TimeoutError:
                    # Heartbeat to keep the connection alive
                    yield ServerSentEvent(
                        data={
                            "timestamp": datetime.datetime.now(
                                datetime.UTC
                            ).isoformat(),
                            "task_id": task_id,
                        },
                        event="ping",
                    )
                    continue

                # Drain currently queued events
                events_to_emit = self.new_events
                self.new_events = []
                # Reset the event flag (more events may arrive after this)
                self._events_available.clear()

                # Yield only events related to this task, but keep history of all
                for ev in events_to_emit:
                    try:
                        self.events.append(ev)
                    except Exception as e:
                        # Never let history tracking break streaming
                        logger.error(
                            f"'submit_and_stream': exception for task '{task_id}' with error: '{e}'"
                        )
                        pass
                    try:
                        if (
                            isinstance(ev.data, dict)
                            and ev.data.get("task_id") == task_id
                        ):  # type: ignore
                            yield ev
                    except Exception as e:
                        # Be tolerant to malformed event data
                        logger.error(
                            f"'submit_and_stream': exception for task '{task_id}' with error: '{e}'"
                        )
                        continue

            # Future completed; emit a final task_complete event with the response body
            try:
                response = future.result()
                yield ServerSentEvent(
                    data={
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                        "task_id": task_id,
                        "response": response["message"]["body"],
                    },
                    event="task_complete",
                )
            except Exception as e:
                # If retrieving the response fails, still signal completion
                logger.error(
                    f"'submit_and_stream': exception for task '{task_id}' with error: '{e}'"
                )
                yield ServerSentEvent(
                    data={
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                        "task_id": task_id,
                        "response": f"{e}",
                    },
                    event="task_error",
                )

        except TimeoutError:
            self.pending_requests.pop(task_id, None)
            logger.error(f"'submit_and_stream': timeout for task '{task_id}'")
            yield ServerSentEvent(
                data={
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "task_id": task_id,
                    "response": "timeout",
                },
                event="task_error",
            )

        except Exception as e:
            self.pending_requests.pop(task_id, None)
            logger.error(
                f"'submit_and_stream': exception for task '{task_id}' with error: '{e}'"
            )
            yield ServerSentEvent(
                data={
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "task_id": task_id,
                    "response": f"{e}",
                },
                event="task_error",
            )

    async def shutdown(self) -> None:
        """
        Request a graceful shutdown of the MAIL system.
        """
        logger.info(f"requesting shutdown for user '{self.user_id}'...")

        # Stop interswarm messaging first
        if self.enable_interswarm:
            await self.stop_interswarm()

        self.shutdown_event.set()

    async def _graceful_shutdown(self) -> None:
        """
        Perform graceful shutdown operations.
        """
        logger.info("starting graceful shutdown...")

        # Graceful shutdown: wait for all active tasks to complete
        if self.active_tasks:
            logger.info(
                f"waiting for {len(self.active_tasks)} active tasks to complete for user '{self.user_id}'..."
            )
            # Copy the set to avoid modification during iteration
            tasks_to_wait = list(self.active_tasks)
            logger.info(
                f"tasks to wait for for user '{self.user_id}': {[task.get_name() if hasattr(task, 'get_name') else str(task) for task in tasks_to_wait]}"
            )

            try:
                # Wait for tasks with a timeout of 30 seconds
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_wait, return_exceptions=True), timeout=30.0
                )
                logger.info(f"all active tasks completed for user '{self.user_id}'")
            except TimeoutError:
                logger.info(
                    f"timeout waiting for tasks to complete for user '{self.user_id}'. cancelling remaining tasks..."
                )
                # Cancel any remaining tasks
                for task in tasks_to_wait:
                    if not task.done():
                        logger.info(
                            f"cancelling task for user '{self.user_id}': {task}"
                        )
                        task.cancel()
                # Wait a bit more for cancellation to complete
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks_to_wait, return_exceptions=True),
                        timeout=5.0,
                    )
                except TimeoutError:
                    logger.info(
                        f"some tasks could not be cancelled cleanly for user '{self.user_id}'"
                    )
                logger.info(f"task cancellation completed for user '{self.user_id}'")
            except Exception as e:
                logger.error(f"error during shutdown for user '{self.user_id}': {e}")
        else:
            logger.info(f"user '{self.user_id}' has no active tasks to wait for")

        logger.info(f"graceful shutdown completed for user '{self.user_id}'")

    async def submit(self, message: MAILMessage) -> None:
        """
        Add a message to the priority queue
        Priority order:
        1. System message of any type
        2. Interrupt, broadcast_complete
        3. Broadcast
        4. Request, response
        Within each category, messages are processed in FIFO order using a
        monotonically increasing sequence number to avoid dict comparisons.
        """
        recipients = (
            message["message"]["recipients"]  # type: ignore
            if "recipients" in message["message"]
            else [message["message"]["recipient"]]
        )
        logger.info(
            f'submitting message: "{message["message"]["sender"]}" -> "{[recipient["address"] for recipient in recipients]}" with subject "{message["message"]["subject"]}"'
        )

        priority = 0
        match message["msg_type"]:
            case "interrupt" | "broadcast_complete":
                priority = 1
            case "broadcast":
                priority = 2
            case "request" | "response":
                priority = 3

        # Monotonic sequence to break ties for same priority
        self._message_seq += 1
        seq = self._message_seq

        await self.message_queue.put((priority, seq, message))

        return

    async def _process_message(
        self,
        message: MAILMessage,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        The internal process for sending a message to the recipient agent(s)
        """
        # If interswarm messaging is enabled, try to route via interswarm router first
        if self.enable_interswarm and self.interswarm_router:
            # Check if any recipients are in interswarm format
            msg_content = message["message"]
            has_interswarm_recipients = False

            if "recipients" in msg_content:
                for recipient in msg_content["recipients"]:  # type: ignore
                    _, recipient_swarm = parse_agent_address(recipient["address"])
                    if recipient_swarm and recipient_swarm != self.swarm_name:
                        has_interswarm_recipients = True
                        break
            elif "recipient" in msg_content:
                _, recipient_swarm = parse_agent_address(
                    msg_content["recipient"]["address"]
                )
                if recipient_swarm and recipient_swarm != self.swarm_name:
                    has_interswarm_recipients = True

            if has_interswarm_recipients:
                # Route via interswarm router. Mark this queue item as handled
                # here; the routed response (or local copy) will be re-submitted
                # via the normal submit() path and accounted for separately.
                asyncio.create_task(self._route_interswarm_message(message))
                try:
                    self.message_queue.task_done()
                except Exception:
                    pass
                return

        # Fall back to local processing
        await self._process_local_message(message, action_override)

    async def _route_interswarm_message(self, message: MAILMessage) -> None:
        """
        Route a message via interswarm router.
        """
        if self.interswarm_router:
            try:
                response = await self.interswarm_router.route_message(message)
                logger.info(
                    f"received response from remote swarm for task '{response['message']['task_id']}', considering local handling"
                )

                # If this response corresponds to an active user task and is
                # addressed to our entrypoint (e.g., supervisor), auto-complete
                # the task instead of re-invoking the agent to avoid ping-pong.
                try:
                    if response.get("msg_type") == "response" and isinstance(
                        response.get("message", {}), dict
                    ):
                        msg = response["message"]
                        task_id = msg.get("task_id")
                        recipient = msg.get("recipient", {})
                        sender_swarm = msg.get("sender_swarm")

                        # recipient is a MAILAddress dict with `address`
                        recipient_addr = (
                            recipient.get("address")
                            if isinstance(recipient, dict)
                            else None
                        )

                        should_autocomplete = (
                            task_id in self.pending_requests
                            and isinstance(recipient_addr, str)
                            and recipient_addr.split("@")[0] == self.entrypoint
                            and sender_swarm is not None
                            and sender_swarm != self.swarm_name
                        )

                        if should_autocomplete and task_id is not None:
                            # Build a broadcast_complete-style message for consistency
                            complete_message = MAILMessage(
                                id=str(uuid.uuid4()),
                                timestamp=datetime.datetime.now(
                                    datetime.UTC
                                ).isoformat(),
                                message=MAILBroadcast(
                                    task_id=task_id,
                                    broadcast_id=str(uuid.uuid4()),
                                    sender=create_agent_address(self.entrypoint),
                                    recipients=[create_agent_address("all")],
                                    subject="Task complete",
                                    body=msg.get("body", "(empty body)"),
                                    sender_swarm=self.swarm_name,
                                    recipient_swarms=[self.swarm_name],
                                    routing_info={},
                                ),
                                msg_type="broadcast_complete",
                            )

                            # Resolve the pending future immediately to end the task
                            future = self.pending_requests.pop(task_id)
                            if not future.done():
                                logger.info(
                                    f"auto-completing task '{task_id}' from interswarm response to '{recipient_addr}'"
                                )
                                future.set_result(complete_message)
                            else:
                                logger.warning(
                                    f"future for task '{task_id}' already done when auto-completing"
                                )

                            # Do not enqueue the raw response; we've completed the task
                            return

                except Exception as e:
                    logger.error(f"error during interswarm auto-complete check: '{e}'")
                    self._submit_event(
                        "router_error",
                        message["message"]["task_id"],
                        f"error during interswarm auto-complete check: '{e}'",
                    )
                    await self.submit(
                        self._system_response(
                            task_id=message["message"]["task_id"],
                            recipient=message["message"]["sender"],
                            subject="Router Error",
                            body=f"""An error occurred while auto-completing task '{task_id}' from interswarm response to '{recipient_addr}'.
The MAIL interswarm router encountered the following error: '{e}'
Use this information to decide how to complete your task.""",
                        )
                    )

                # Default behavior: enqueue response for local processing
                await self.submit(response)
            except Exception as e:
                logger.error(f"error in interswarm routing: '{e}'")

                self._submit_event(
                    "router_error",
                    message["message"]["task_id"],
                    f"error in interswarm routing: '{e}'",
                )

                # inform the sender that the message was not delivered
                await self.submit(
                    self._system_response(
                        task_id=message["message"]["task_id"],
                        recipient=message["message"]["sender"],
                        subject="Router Error",
                        body=f"""Your message to '{message["message"]["sender"]["address"]}' was not delivered. 
The MAIL interswarm router encountered the following error: '{e}'
If your assigned task cannot be completed, inform your caller of this error and work together to come up with a solution.""",
                    )
                )
        else:
            logger.error("interswarm router not available")

            self._submit_event(
                "router_error",
                message["message"]["task_id"],
                "interswarm router not available",
            )

            # inform the sender that the message was not delivered
            await self.submit(
                self._system_response(
                    task_id=message["message"]["task_id"],
                    recipient=message["message"]["sender"],
                    subject="Router Error",
                    body=f"""Your message to '{message["message"]["sender"]["address"]}' was not delivered. 
The MAIL interswarm router is not currently available.
If your assigned task cannot be completed, inform your caller of this error and work together to come up with a solution.""",
                )
            )

    async def _process_local_message(
        self,
        message: MAILMessage,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        Process a message locally (original _process_message logic)
        """
        msg_content = message["message"]

        if "recipients" in msg_content:
            if msg_content["recipients"] == ["all"]:  # type: ignore
                recipients = list(self.agents.keys())
                recipients.remove(message["message"]["sender"]["address"])
            else:
                recipients = [agent["address"] for agent in msg_content["recipients"]]  # type: ignore
        else:
            recipients = [msg_content["recipient"]["address"]]

        for recipient in recipients:
            # Parse recipient address to get local agent name
            recipient_agent, recipient_swarm = parse_agent_address(recipient)

            # Only process if this is a local agent or no swarm specified
            if not recipient_swarm or recipient_swarm == self.swarm_name:
                if recipient_agent in self.agents:
                    self._send_message(recipient_agent, message, action_override)
                else:
                    logger.warning(f"unknown local agent: '{recipient_agent}'")
                    sender_agent = message["message"]["sender"]["address"]

                    # if the recipient is actually the user, indicate that
                    if recipient_agent == self.user_id:
                        self._submit_event(
                            "agent_error",
                            message["message"]["task_id"],
                            f"agent '{message['message']['sender']['address']}' attempted to send a message to the user ('{self.user_id}')",
                        )
                        self._send_message(
                            sender_agent,
                            self._system_response(
                                task_id=message["message"]["task_id"],
                                recipient=create_agent_address(recipient),
                                subject="Improper response to user",
                                body=f"""The user ('{self.user_id}') is unable to respond to your message. 
If the user's task is complete, use the 'task_complete' tool.
Otherwise, continue working with your agents to complete the user's task.""",
                            ),
                            action_override,
                        )
                    elif recipient_agent == self.swarm_name:
                        self._submit_event(
                            "task_error",
                            message["message"]["task_id"],
                            f"agent '{recipient_agent}' is the swarm name; message from '{message['message']['sender']['address']}' cannot be delivered to it",
                        )
                        await self.submit(
                            self._system_broadcast(
                                task_id=message["message"]["task_id"],
                                subject="Error: System-to-system message",
                                body=f"""A message was detected with sender '{message["message"]["sender"]["address"]}' and recipient '{recipient_agent}'.
This likely means that an error message intended for an agent was sent to the system.
This, in turn, was probably caused by an agent failing to respond to a system response.
In order to prevent infinite loops, system-to-system messages immediately end the task.""",
                                task_complete=True,
                            )
                        )
                        return None
                    else:
                        # otherwise, just a normal unknown agent
                        self._submit_event(
                            "agent_error",
                            message["message"]["task_id"],
                            f"agent '{recipient_agent}' is unknown; message from '{message['message']['sender']['address']}' cannot be delivered to it",
                        )
                        self._send_message(
                            sender_agent,
                            self._system_response(
                                task_id=message["message"]["task_id"],
                                recipient=create_agent_address(recipient),
                                subject=f"Unknown Agent: '{recipient_agent}'",
                                body=f"""The agent '{recipient_agent}' is not known to this swarm.
Your directly reachable agents can be found in the tool definitions for `send_request` and `send_response`.""",
                            ),
                            action_override,
                        )
            else:
                logger.debug(f"skipping remote agent '{recipient}' in local processing")

        return None

    def _send_message(
        self,
        recipient: str,
        message: MAILMessage,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        Send a message to a recipient.
        """
        logger.info(
            f'sending message: "{message["message"]["sender"]}" -> "{recipient}" with subject: "{message["message"]["subject"]}"'
        )
        self._submit_event(
            "new_message",
            message["message"]["task_id"],
            f"sending message:\n{build_mail_xml(message)['content']}",
        )

        async def schedule(message: MAILMessage) -> None:
            """
            Schedule a message for processing.
            Agent functions are called here.
            """
            try:
                # prepare the message for agent input
                task_id = message["message"]["task_id"]
                history = self.agent_histories[recipient]
                if not message["message"]["subject"].startswith(
                    "::action_complete_broadcast::"
                ):
                    incoming_message = build_mail_xml(message)
                    history.append(incoming_message)

                # agent function is called here
                out, results = await self.agents[recipient](history, "required")

                # append the agent's response to the history
                if results[0].completion:
                    history.append(results[0].completion)
                else:
                    history.extend(results[0].responses)

                # append the agent's tool responses to the history
                for tc in results:
                    if tc.tool_name in MAIL_TOOL_NAMES:
                        result_message = tc.create_response_msg(
                            "Message sent. The response, if any, will be sent in the next user message."
                        )
                        history.append(result_message)

                # handle tool calls
                for call in results:
                    match call.tool_name:
                        case "acknowledge_broadcast":
                            try:
                                # Only store if this was a broadcast; otherwise treat as no-op
                                if message["msg_type"] == "broadcast":
                                    note = call.tool_args.get("note")
                                    async with get_langmem_store() as store:
                                        manager = create_memory_store_manager(
                                            "anthropic:claude-sonnet-4-20250514",
                                            query_model="anthropic:claude-sonnet-4-20250514",
                                            query_limit=10,
                                            namespace=(f"{recipient}_memory",),
                                            store=store,
                                        )
                                        assistant_content = (
                                            f"<acknowledged broadcast/>\n{note}".strip()
                                            if note
                                            else "<acknowledged broadcast/>"
                                        )
                                        await manager.ainvoke(
                                            {
                                                "messages": [
                                                    {
                                                        "role": "user",
                                                        "content": incoming_message[
                                                            "content"
                                                        ],
                                                    },
                                                    {
                                                        "role": "assistant",
                                                        "content": assistant_content,
                                                    },
                                                ]
                                            }
                                        )
                                else:
                                    logger.debug(
                                        f"agent '{recipient}' used 'acknowledge_broadcast' on a '{message['msg_type']}'"
                                    )
                                    await self.submit(
                                        self._system_response(
                                            task_id=task_id,
                                            recipient=create_agent_address(recipient),
                                            subject="Improper use of `acknowledge_broadcast`",
                                            body=f"""The `acknowledge_broadcast` tool cannot be used in response to a message of type '{message["msg_type"]}'.
If your sender's message is a 'request', consider using `send_response` instead.
Otherwise, determine the best course of action to complete your task.""",
                                        )
                                    )
                            except Exception as e:
                                logger.error(
                                    f"error acknowledging broadcast for agent '{recipient}': '{e}'"
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"error acknowledging broadcast for agent '{recipient}': '{e}'",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject=f"Error acknowledging broadcast from '{message['message']['sender']['address']}'",
                                        body=f"""An error occurred while acknowledging the broadcast from '{message["message"]["sender"]["address"]}'.
Specifically, the MAIL runtime encountered the following error: '{e}'.
It is possible that the `acknowledge_broadcast` tool is not implemented properly.
Use this information to decide how to complete your task.""",
                                    )
                                )
                            # No outgoing message submission for acknowledge
                        case "ignore_broadcast":
                            # Explicitly ignore without storing or responding
                            logger.info(
                                "broadcast ignored by agent via ignore_broadcast tool"
                            )
                            # No further action
                        case "send_request":
                            await self.submit(
                                convert_call_to_mail_message(call, recipient, task_id)
                            )
                        case "send_response":
                            await self.submit(
                                convert_call_to_mail_message(call, recipient, task_id)
                            )
                        case "send_interrupt":
                            await self.submit(
                                convert_call_to_mail_message(call, recipient, task_id)
                            )
                        case "send_broadcast":
                            await self.submit(
                                convert_call_to_mail_message(call, recipient, task_id)
                            )
                        case "task_complete":
                            # Check if this completes a pending request
                            if task_id and task_id in self.pending_requests:
                                logger.info(
                                    f"task '{task_id}' completed, resolving pending request for user '{self.user_id}'"
                                )
                                # Create a response message for the user
                                response_message = MAILMessage(
                                    id=str(uuid.uuid4()),
                                    timestamp=datetime.datetime.now(
                                        datetime.UTC
                                    ).isoformat(),
                                    message=MAILBroadcast(
                                        task_id=task_id,
                                        broadcast_id=str(uuid.uuid4()),
                                        sender=create_agent_address(self.entrypoint),
                                        recipients=[create_agent_address("all")],
                                        subject="Task complete",
                                        body=call.tool_args.get(
                                            "finish_message",
                                            "Task completed successfully",
                                        ),
                                        sender_swarm=self.swarm_name,
                                        recipient_swarms=[self.swarm_name],
                                        routing_info={},
                                    ),
                                    msg_type="broadcast_complete",
                                )
                                # Resolve the pending request
                                future = self.pending_requests.pop(task_id)
                                if not future.done():
                                    logger.info(
                                        f"resolving future for task '{task_id}'"
                                    )
                                    future.set_result(response_message)
                                else:
                                    logger.warning(
                                        f"future for task '{task_id}' was already done"
                                    )
                                # Don't submit the duplicate message - we've already resolved the request
                            else:
                                logger.info(
                                    f"task '{task_id}' completed but no pending request found, submitting message"
                                )
                                # Only submit the message if there's no pending request to resolve
                                await self.submit(
                                    convert_call_to_mail_message(
                                        call, recipient, task_id
                                    )
                                )
                        case _:
                            logger.info(
                                f"agent '{recipient}' executing action tool: '{call.tool_name}'"
                            )
                            self._submit_event(
                                "action_call",
                                task_id,
                                f"agent '{recipient}' executing action tool: '{call.tool_name}'",
                            )
                            try:
                                result_message = await execute_action_tool(
                                    call, self.actions, action_override
                                )
                                history.append(result_message)
                                result_content = (
                                    result_message.get("content")
                                    if call.completion
                                    else result_message.get("output")
                                )
                                self._submit_event(
                                    "action_complete",
                                    task_id,
                                    f"action complete (caller = '{recipient}'):\n'{result_content}'",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::action_complete_broadcast::",
                                        body="",
                                        recipients=[create_agent_address(recipient)],
                                    )
                                )
                            except Exception as e:
                                logger.error(f"error executing action tool: '{e}'")
                                self._submit_event(
                                    "action_error",
                                    task_id,
                                    f"action error (caller = '{recipient}'):\n'{e}'",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject=f"Error executing action tool `{call.tool_name}`",
                                        body=f"""An error occurred while executing the action tool `{call.tool_name}`.
Specifically, the MAIL runtime encountered the following error: '{e}'.
It is possible that the action tool `{call.tool_name}` is not implemented properly.
Use this information to decide how to complete your task.""",
                                        recipients=[create_agent_address(recipient)],
                                    )
                                )

                self.agent_histories[recipient] = history
            except Exception as e:
                logger.error(f"error scheduling message for agent '{recipient}': '{e}'")
                self._submit_event(
                    "agent_error",
                    task_id,
                    f"error scheduling message for recipient '{recipient}': '{e}'",
                )
                await self.submit(
                    self._system_response(
                        task_id=task_id,
                        recipient=message["message"]["sender"],
                        subject=f"Agent Error: '{recipient}'",
                        body=f"""An error occurred while scheduling the message for agent '{recipient}'.
Specifically, the MAIL runtime encountered the following error: '{e}'.
It is possible that the agent function for '{recipient}' is not valid.
Use this information to decide how to complete your task.""",
                    )
                )
            finally:
                self.message_queue.task_done()

        task = asyncio.create_task(schedule(message))
        self.active_tasks.add(task)

        task.add_done_callback(self.active_tasks.discard)

        return None

    def _system_broadcast(
        self,
        task_id: str,
        subject: str,
        body: str,
        task_complete: bool = False,
        recipients: list[MAILAddress] | None = None,
    ) -> MAILMessage:
        """
        Create a system broadcast message.
        """
        if recipients is None and not task_complete:
            raise ValueError(
                "recipients must be provided for non-task-complete broadcasts"
            )

        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILBroadcast(
                task_id=task_id,
                broadcast_id=str(uuid.uuid4()),
                sender=create_system_address(self.swarm_name),
                recipients=[create_agent_address("all")]
                if task_complete
                else (recipients or []),
                subject=subject,
                body=body,
                sender_swarm=self.swarm_name,
                recipient_swarms=[self.swarm_name],
                routing_info={},
            ),
            msg_type="broadcast" if not task_complete else "broadcast_complete",
        )

    def _system_response(
        self,
        task_id: str,
        subject: str,
        body: str,
        recipient: MAILAddress,
    ) -> MAILMessage:
        """
        Create a system response message for a recipient.
        Said recipient must be either an agent or the user.
        """
        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILResponse(
                task_id=task_id,
                request_id=str(uuid.uuid4()),
                sender=create_system_address(self.swarm_name),
                recipient=recipient,
                subject=subject,
                body=body,
                sender_swarm=self.swarm_name,
                recipient_swarm=self.swarm_name,
                routing_info={},
            ),
            msg_type="response",
        )

    def _submit_event(self, event: str, task_id: str, description: str) -> None:
        """
        Submit an event to the event queue.
        """
        self.new_events.append(
            ServerSentEvent(
                data={
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "description": description,
                    "task_id": task_id,
                },
                event=event,
            )
        )
        # Signal that new events are available for streaming
        try:
            self._events_available.set()
        except Exception:
            pass
        return None

    def get_events_by_task_id(self, task_id: str) -> list[ServerSentEvent]:
        """
        Get events by task ID.
        """
        candidates = []
        try:
            candidates.extend(self.events)
        except Exception:
            pass
        try:
            candidates.extend(self.new_events)
        except Exception:
            pass
        out = []
        for ev in candidates:
            try:
                if isinstance(ev.data, dict) and ev.data.get("task_id") == task_id:
                    out.append(ev)
            except Exception:
                continue
        return out
