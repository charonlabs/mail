# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import datetime
import json
import logging
import uuid
from asyncio import PriorityQueue, Task
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any, Literal

from langmem import create_memory_store_manager
from sse_starlette import ServerSentEvent
import ujson

from mail.net import InterswarmRouter, SwarmRegistry
from mail.utils.serialize import _REDACT_KEYS, _format_event_sections, _serialize_event
from mail.utils.store import get_langmem_store
from mail.utils.string_builder import build_mail_help_string

from .actions import (
    ActionCore,
    ActionOverrideFunction,
)
from .agents import (
    AgentCore,
)
from .message import (
    MAIL_ALL_LOCAL_AGENTS,
    MAILAddress,
    MAILBroadcast,
    MAILMessage,
    MAILResponse,
    build_mail_xml,
    create_agent_address,
    create_system_address,
    parse_agent_address,
)
from .tasks import MAILTask
from .tools import (
    AgentToolCall,
    convert_call_to_mail_message,
)

logger = logging.getLogger("mail.runtime")

AGENT_HISTORY_KEY = "{task_id}::{agent_name}"


class MAILRuntime:
    """
    Runtime for an individual MAIL swarm instance.
    Handles the local message queue and provides an action executor for tools.
    """

    def __init__(
        self,
        agents: dict[str, AgentCore],
        actions: dict[str, ActionCore],
        user_id: str,
        swarm_name: str,
        entrypoint: str,
        swarm_registry: SwarmRegistry | None = None,
        enable_interswarm: bool = False,
        breakpoint_tools: list[str] = [],
        exclude_tools: list[str] = [],
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
        # Agent histories in an LLM-friendly format
        self.agent_histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # MAIL tasks in swarm memory
        self.mail_tasks: dict[str, MAILTask] = {}
        # asyncio tasks that are currently active
        self.active_tasks: set[Task[Any]] = set()
        self.shutdown_event = asyncio.Event()
        self.is_running = False
        self.pending_requests: dict[str, asyncio.Future[MAILMessage]] = {}
        self.user_id = user_id
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
        self.breakpoint_tools = breakpoint_tools
        self._is_continuous = False
        self.exclude_tools = exclude_tools
        self.response_messages: dict[str, MAILMessage] = {}
        self.last_breakpoint_caller: str | None = None
        self.last_breakpoint_tool_calls: list[AgentToolCall] = []

    def _log_prelude(self) -> str:
        """
        Build the string that will be prepended to all log messages.
        """
        return f"[{self.user_id}@{self.swarm_name}]"

    async def start_interswarm(self) -> None:
        """
        Start interswarm messaging capabilities.
        """
        if self.enable_interswarm and self.interswarm_router:
            await self.interswarm_router.start()
            logger.info(f"{self._log_prelude()} started interswarm messaging")

    async def stop_interswarm(self) -> None:
        """
        Stop interswarm messaging capabilities.
        """
        if self.interswarm_router:
            await self.interswarm_router.stop()
            logger.info(f"{self._log_prelude()} stopped interswarm messaging")

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
        logger.info(
            f"{self._log_prelude()} handling interswarm response with task ID '{response_message['message']['task_id']}'"
        )

        # Submit the response to the local message queue for processing
        # This will allow the local supervisor agent to process the response
        # and generate a final response for the user
        await self.submit(response_message)

        # Don't immediately complete the pending request here
        # Let the local processing flow handle it naturally
        # The supervisor agent should process the response and generate
        # a final response that will complete the user's request

    async def run_task(
        self,
        task_id: str | None = None,
        action_override: ActionOverrideFunction | None = None,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        max_steps: int | None = None,
        **kwargs: Any,
    ) -> MAILMessage:
        """
        Run the MAIL system until the specified task is complete or shutdown is requested.
        This method can be called multiple times for different requests.
        """
        match resume_from:
            case "user_response":
                if task_id is None:
                    logger.error(
                        f"{self._log_prelude()} task_id is required when resuming from a user response"
                    )
                    return self._system_broadcast(
                        task_id="null",
                        subject="::runtime_error::",
                        body="""The parameter 'task_id' is required when resuming from a user response.
It is impossible to resume a task without `task_id` specified.""",
                        task_complete=True,
                    )
                if task_id not in self.mail_tasks:
                    logger.error(f"{self._log_prelude()} task '{task_id}' not found")
                    return self._system_broadcast(
                        task_id=task_id,
                        subject="::runtime_error::",
                        body=f"The task '{task_id}' was not found.",
                        task_complete=True,
                    )

                await self.mail_tasks[task_id].queue_load(self.message_queue)
                self.mail_tasks[task_id].is_running = True

                try:
                    result = await self._run_loop_for_task(task_id, action_override)
                finally:
                    self.mail_tasks[task_id].is_running = False

            case "breakpoint_tool_call":
                if task_id is None:
                    logger.error(
                        f"{self._log_prelude()} task_id is required when resuming from a breakpoint tool call"
                    )
                    return self._system_broadcast(
                        task_id="null",
                        subject="::runtime_error::",
                        body="""The parameter 'task_id' is required when resuming from a breakpoint tool call.
It is impossible to resume a task without `task_id` specified.""",
                        task_complete=True,
                    )
                if task_id not in self.mail_tasks:
                    logger.error(f"{self._log_prelude()} task '{task_id}' not found")
                    return self._system_broadcast(
                        task_id=task_id,
                        subject="::runtime_error::",
                        body=f"The task '{task_id}' was not found.",
                        task_complete=True,
                    )

                REQUIRED_KWARGS = [
                    "breakpoint_tool_call_result",
                ]
                for kwarg in REQUIRED_KWARGS:
                    if kwarg not in kwargs:
                        logger.error(
                            f"{self._log_prelude()} required keyword argument '{kwarg}' not provided"
                        )
                        return self._system_broadcast(
                            task_id=task_id,
                            subject="Runtime Error",
                            body=f"""The keyword argument '{kwarg}' is required when resuming from a breakpoint tool call.
It is impossible to resume a task without `{kwarg}` specified.""",
                            task_complete=True,
                        )
                if self.last_breakpoint_caller is None:
                    logger.error(
                        f"{self._log_prelude()} last breakpoint caller is not set"
                    )
                    return self._system_broadcast(
                        task_id=task_id,
                        subject="::runtime_error::",
                        body="The last breakpoint caller is not set.",
                        task_complete=True,
                    )
                breakpoint_tool_caller = self.last_breakpoint_caller
                breakpoint_tool_call_result = kwargs["breakpoint_tool_call_result"]

                result = await self._resume_task_from_breakpoint_tool_call(
                    task_id,
                    breakpoint_tool_caller,
                    breakpoint_tool_call_result,
                    action_override=action_override,
                )

            case None:  # start a new task
                if task_id is None:
                    task_id = str(uuid.uuid4())
                self._ensure_task_exists(task_id)

                self.mail_tasks[task_id].is_running = True

                try:
                    result = await self._run_loop_for_task(
                        task_id, action_override, max_steps
                    )
                finally:
                    self.mail_tasks[task_id].is_running = False

        return result

    async def _run_loop_for_task(
        self,
        task_id: str,
        action_override: ActionOverrideFunction | None = None,
        max_steps: int | None = None,
    ) -> MAILMessage:
        """
        Run the MAIL system for a specific task until the task is complete or shutdown is requested.
        """
        steps = 0
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
                    logger.info(f"{self._log_prelude()} shutdown requested")
                    return self._system_broadcast(
                        task_id="null",
                        subject="::shutdown_requested::",
                        body="The shutdown was requested.",
                        task_complete=True,
                    )

                # Process the message
                message_tuple = get_message_task.result()
                # message_tuple structure: (priority, seq, message)
                message = message_tuple[2]
                logger.info(
                    f"{self._log_prelude()} processing message with task ID '{message['message']['task_id']}': '{message['message']['subject']}'"
                )
                if message["msg_type"] == "broadcast_complete":
                    task_id_completed = message["message"].get("task_id")
                    if isinstance(task_id_completed, str):
                        self.response_messages[task_id_completed] = message
                        self._ensure_task_exists(task_id_completed)
                        await self.mail_tasks[task_id_completed].queue_stash(
                            self.message_queue
                        )
                    # Mark this message as done before breaking
                    self.message_queue.task_done()
                    return message

                if (
                    not message["message"]["subject"].startswith("::")
                    and not message["message"]["sender"]["address_type"] == "system"
                ):
                    steps += 1
                    if max_steps is not None and steps > max_steps:
                        ev = self.get_events_by_task_id(task_id)
                        serialized_events = []
                        for event in ev:
                            serialized = _serialize_event(
                                event, exclude_keys=_REDACT_KEYS
                            )
                            if serialized is not None:
                                serialized_events.append(serialized)
                        event_sections = _format_event_sections(serialized_events)
                        message = self._system_response(
                            task_id=task_id,
                            subject="::maximum_steps_reached::",
                            body=f"The swarm has reached the maximum number of steps allowed. You must now call `task_complete` and provide a response to the best of your ability. Below is a transcript of the entire swarm conversation for context:\n\n{event_sections}",
                            recipient=create_agent_address(self.entrypoint),
                        )
                        logger.info(
                            f"{self._log_prelude()} maximum number of steps reached for task '{task_id}', sending system response"
                        )

                await self._process_message(message, action_override)
                # Note: task_done() is called by the schedule function for regular messages

            except asyncio.CancelledError:
                logger.info(
                    f"{self._log_prelude()} run loop cancelled, initiating shutdown..."
                )
                self._submit_event(
                    "run_loop_cancelled",
                    message["message"]["task_id"],
                    "run loop cancelled",
                )
                return self._system_broadcast(
                    task_id=message["message"]["task_id"],
                    subject="::run_loop_cancelled::",
                    body="The run loop was cancelled.",
                    task_complete=True,
                )
            except Exception as e:
                logger.error(f"{self._log_prelude()} error in run loop: '{e}'")
                self._submit_event(
                    "run_loop_error",
                    message["message"]["task_id"],
                    f"error in run loop: '{e}'",
                )
                return self._system_broadcast(
                    task_id=message["message"]["task_id"],
                    subject="::run_loop_error::",
                    body=f"An error occurred while running the MAIL system: '{e}'",
                    task_complete=True,
                )

    async def _resume_task_from_breakpoint_tool_call(
        self,
        task_id: str,
        breakpoint_tool_caller: Any,
        breakpoint_tool_call_result: Any,
        action_override: ActionOverrideFunction | None = None,
    ) -> MAILMessage:
        """
        Resume a task from a breakpoint tool call.
        """
        if (
            not isinstance(breakpoint_tool_call_result, str)
            and not isinstance(breakpoint_tool_call_result, list)
            and not isinstance(breakpoint_tool_call_result, dict)
        ):
            logger.error(
                f"{self._log_prelude()} breakpoint_tool_call_result must be a string, list, or dict"
            )
            return self._system_broadcast(
                task_id=task_id,
                subject="::runtime_error::",
                body="""The parameter 'breakpoint_tool_call_result' must be a string, list, or dict.
`breakpoint_tool_call_result` specifies the result of the breakpoint tool call.""",
                task_complete=True,
            )
        if breakpoint_tool_caller not in self.agents:
            logger.error(
                f"{self._log_prelude()} agent '{breakpoint_tool_caller}' not found"
            )
            return self._system_broadcast(
                task_id=task_id,
                subject="::runtime_error::",
                body=f"The agent '{breakpoint_tool_caller}' was not found.",
                task_complete=True,
            )

        await self.mail_tasks[task_id].queue_load(self.message_queue)
        result_msgs: list[dict[str, Any]] = []
        if isinstance(breakpoint_tool_call_result, str):
            payload = ujson.loads(breakpoint_tool_call_result)
        else:
            payload = breakpoint_tool_call_result

        if isinstance(payload, list):
            for resp in payload:
                og_call = next(
                    (
                        call
                        for call in self.last_breakpoint_tool_calls
                        if call.tool_call_id == resp["call_id"]
                    ),
                    None,
                )
                if og_call is not None:
                    result_msgs.append(og_call.create_response_msg(resp["content"]))
        else:
            if len(self.last_breakpoint_tool_calls) > 1:
                logger.error(
                    f"{self._log_prelude()} last breakpoint tool calls is a list but only one call response was provided"
                )
                return self._system_broadcast(
                    task_id=task_id,
                    subject="::runtime_error::",
                    body="The last breakpoint tool calls is a list but only one call response was provided.",
                    task_complete=True,
                )
            result_msgs.append(
                self.last_breakpoint_tool_calls[0].create_response_msg(
                    payload["content"]
                )
            )
        for result_msg in result_msgs:
            self._submit_event(
                "breakpoint_action_complete",
                task_id,
                f"breakpoint action complete(caller = '{breakpoint_tool_caller}'):\n'{result_msg['content']}'",
            )

        # append the breakpoint tool call result to the agent history
        self.agent_histories[
            AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=breakpoint_tool_caller)
        ].extend(result_msgs)

        # send action complete broadcast to tool caller
        await self.submit(
            self._system_broadcast(
                task_id=task_id,
                subject="::action_complete_broadcast::",
                body="",
                recipients=[create_agent_address(breakpoint_tool_caller)],
            )
        )

        # resume the task
        self.mail_tasks[task_id].is_running = True
        try:
            result = await self._run_loop_for_task(task_id, action_override)
        finally:
            self.mail_tasks[task_id].is_running = False

        return result

    async def run_continuous(
        self,
        max_steps: int | None = None,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        Run the MAIL system continuously, handling multiple requests.
        This method runs indefinitely until shutdown is requested.
        """
        logger.info(
            f"{self._log_prelude()} starting continuous MAIL operation for user '{self.user_id}'..."
        )
        self._is_continuous = True
        steps = 0
        while not self.shutdown_event.is_set():
            try:
                logger.debug(
                    f"{self._log_prelude()} pending requests: {self.pending_requests.keys()}"
                )

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
                        f"{self._log_prelude()} shutdown requested in continuous mode"
                    )
                    self._submit_event(
                        "shutdown_requested",
                        "*",
                        "shutdown requested in continuous mode",
                    )
                    break

                # Process the message
                message_tuple = get_message_task.result()
                # message_tuple structure: (priority, seq, message)
                message = message_tuple[2]
                logger.info(
                    f"{self._log_prelude()} processing message with task ID '{message['message']['task_id']}' in continuous mode: '{message['message']['subject']}'"
                )
                task_id = message["message"]["task_id"]

                if message["msg_type"] == "broadcast_complete":
                    # Check if this completes a pending request
                    self.response_messages[task_id] = message
                    if isinstance(task_id, str):
                        self._ensure_task_exists(task_id)
                        await self.mail_tasks[task_id].queue_stash(self.message_queue)
                    if isinstance(task_id, str) and task_id in self.pending_requests:
                        # Resolve the pending request
                        logger.info(
                            f"{self._log_prelude()} task '{task_id}' completed, resolving pending request"
                        )
                        future = self.pending_requests.pop(task_id)
                        future.set_result(message)
                    else:
                        # Mark this message as done and continue processing
                        self.message_queue.task_done()
                        continue

                if (
                    not message["message"]["subject"].startswith("::")
                    and not message["message"]["sender"]["address_type"] == "system"
                ):
                    steps += 1
                    if max_steps is not None and steps > max_steps:
                        ev = self.get_events_by_task_id(task_id)
                        serialized_events = []
                        for event in ev:
                            serialized = _serialize_event(
                                event, exclude_keys=_REDACT_KEYS
                            )
                            if serialized is not None:
                                serialized_events.append(serialized)
                        event_sections = _format_event_sections(serialized_events)
                        message = self._system_response(
                            task_id=task_id,
                            subject="::maximum_steps_reached::",
                            body=f"The swarm has reached the maximum number of steps allowed. You must now call `task_complete` and provide a response to the best of your ability. Below is a transcript of the entire swarm conversation for context:\n\n{event_sections}",
                            recipient=create_agent_address(self.entrypoint),
                        )
                        logger.info(
                            f"{self._log_prelude()} maximum number of steps reached for task '{task_id}', sending system response"
                        )

                await self._process_message(message, action_override)
                # Note: task_done() is called by the schedule function for regular messages

            except asyncio.CancelledError:
                logger.info(f"{self._log_prelude()} continuous run loop cancelled")
                self._submit_event(
                    "run_loop_cancelled",
                    "*",
                    "continuous run loop cancelled",
                )
                self._is_continuous = False
                break
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} error in continuous run loop: '{e}'"
                )
                self._submit_event(
                    "run_loop_error",
                    "*",
                    f"continuous run loop error: '{e}'",
                )
                self._is_continuous = False
                # Continue processing other messages instead of shutting down
                continue

        logger.info(f"{self._log_prelude()} continuous MAIL operation stopped")

    async def submit_and_wait(
        self,
        message: MAILMessage,
        timeout: float = 3600.0,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> MAILMessage:
        """
        Submit a message and wait for the response.
        This method is designed for handling individual task requests in a persistent MAIL instance.
        """
        task_id = message["message"]["task_id"]

        logger.info(
            f"{self._log_prelude()} `submit_and_wait`: creating future for task '{task_id}'"
        )

        # Create a future to wait for the response
        future: asyncio.Future[MAILMessage] = asyncio.Future()
        self.pending_requests[task_id] = future

        try:
            match resume_from:
                case "user_response":
                    await self._submit_user_response(task_id, **kwargs)
                case "breakpoint_tool_call":
                    await self._submit_breakpoint_tool_call_result(task_id, **kwargs)
                case (
                    None
                ):  # start a new task (task_id should be provided in the message)
                    self._ensure_task_exists(task_id)

                    self.mail_tasks[task_id].is_running = True

                    await self.submit(message)

            # Wait for the response with timeout
            logger.info(
                f"{self._log_prelude()} `submit_and_wait`: waiting for future for task '{task_id}'"
            )
            response = await asyncio.wait_for(future, timeout=timeout)
            logger.info(
                f"{self._log_prelude()} `submit_and_wait`: got response for task '{task_id}' with body: '{response['message']['body'][:50]}...'..."
            )
            self._submit_event(
                "task_complete", task_id, f"response: '{response['message']['body']}'"
            )
            self.mail_tasks[task_id].is_running = False

            return response

        except TimeoutError:
            # Remove the pending request
            self.pending_requests.pop(task_id, None)
            logger.error(
                f"{self._log_prelude()} `submit_and_wait`: timeout for task '{task_id}'"
            )
            self._submit_event("task_error", task_id, f"timeout for task '{task_id}'")
            return self._system_broadcast(
                task_id=task_id,
                subject="::task_timeout::",
                body="The task timed out.",
                task_complete=True,
            )
        except Exception as e:
            # Remove the pending request
            self.pending_requests.pop(task_id, None)
            logger.error(
                f"{self._log_prelude()} `submit_and_wait`: exception for task '{task_id}' with error: '{e}'"
            )
            self._submit_event("task_error", task_id, f"error for task: '{e}'")
            return self._system_broadcast(
                task_id=task_id,
                subject="::task_error::",
                body=f"The task encountered an error: '{e}'.",
                task_complete=True,
            )

    async def submit_and_stream(
        self,
        message: MAILMessage,
        timeout: float = 3600.0,
        resume_from: Literal["user_response", "breakpoint_tool_call"] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """
        Submit a message and stream the response.
        This method is designed for handling individual task requests in a persistent MAIL instance.
        """
        task_id = message["message"]["task_id"]

        logger.info(
            f"{self._log_prelude()} `submit_and_stream`: creating future for task '{task_id}'"
        )

        future: asyncio.Future[MAILMessage] = asyncio.Future()
        self.pending_requests[task_id] = future

        try:
            match resume_from:
                case "user_response":
                    await self._submit_user_response(task_id, message, **kwargs)
                case "breakpoint_tool_call":
                    await self._submit_breakpoint_tool_call_result(task_id, **kwargs)
                case None:  # start a new task
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
                        self.mail_tasks[task_id].add_event(ev)
                    except Exception as e:
                        # Never let history tracking break streaming
                        logger.error(
                            f"{self._log_prelude()} `submit_and_stream`: failed to add event to task '{task_id}': '{e}'"
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
                            f"{self._log_prelude()} `submit_and_stream`: failed to yield event for task '{task_id}': '{e}'"
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
                    f"{self._log_prelude()} `submit_and_stream`: exception for task '{task_id}' with error: '{e}'"
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
            logger.error(
                f"{self._log_prelude()} `submit_and_stream`: timeout for task '{task_id}'"
            )
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
                f"{self._log_prelude()} `submit_and_stream`: exception for task '{task_id}' with error: '{e}'"
            )
            yield ServerSentEvent(
                data={
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "task_id": task_id,
                    "response": f"{e}",
                },
                event="task_error",
            )

    async def _submit_user_response(
        self,
        task_id: str,
        message: MAILMessage,
        **kwargs: Any,
    ) -> None:
        """
        Submit a user response to a pre-existing task.
        """
        if task_id not in self.mail_tasks:
            logger.error(
                f"{self._log_prelude()} `submit_user_response`: task '{task_id}' not found"
            )
            raise ValueError(f"task '{task_id}' not found")

        await self.mail_tasks[task_id].queue_load(self.message_queue)

        await self.submit(message)

    async def _submit_breakpoint_tool_call_result(
        self,
        task_id: str,
        **kwargs: Any,
    ) -> None:
        """
        Submit a breakpoint tool call result to the task.
        """
        # ensure the task exists already
        if task_id not in self.mail_tasks:
            logger.error(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: task '{task_id}' not found"
            )
            raise ValueError(f"task '{task_id}' not found")

        # ensure valid kwargs
        REQUIRED_KWARGS: dict[str, type] = {
            "breakpoint_tool_caller": str,
            "breakpoint_tool_call_result": str,
        }
        for kwarg, _type in REQUIRED_KWARGS.items():
            if kwarg not in kwargs:
                logger.error(
                    f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: required keyword argument '{kwarg}' not provided"
                )
                raise ValueError(f"required keyword argument '{kwarg}' not provided")
        breakpoint_tool_caller = kwargs["breakpoint_tool_caller"]
        breakpoint_tool_call_result = kwargs["breakpoint_tool_call_result"]

        # ensure the agent exists already
        if breakpoint_tool_caller not in self.agents:
            logger.error(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: agent '{breakpoint_tool_caller}' not found"
            )
            raise ValueError(f"agent '{breakpoint_tool_caller}' not found")

        # append the breakpoint tool call result to the agent history
        self.agent_histories[
            AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=breakpoint_tool_caller)
        ].append(
            {
                "role": "tool",
                "content": breakpoint_tool_call_result,
            }
        )

        await self.mail_tasks[task_id].queue_load(self.message_queue)

        # submit an action complete broadcast to the task
        await self.submit(
            self._system_broadcast(
                task_id=task_id,
                subject="::action_complete_broadcast::",
                body="",
                recipients=[create_agent_address(breakpoint_tool_caller)],
            )
        )

    async def shutdown(self) -> None:
        """
        Request a graceful shutdown of the MAIL system.
        """
        logger.info(f"{self._log_prelude()} requesting shutdown")
        self._is_continuous = False

        # Stop interswarm messaging first
        if self.enable_interswarm:
            await self.stop_interswarm()

        self.shutdown_event.set()

    async def _graceful_shutdown(self) -> None:
        """
        Perform graceful shutdown operations.
        """
        logger.info(f"{self._log_prelude()} starting graceful shutdown")

        # Graceful shutdown: wait for all active tasks to complete
        if self.active_tasks:
            logger.info(
                f"{self._log_prelude()} waiting for {len(self.active_tasks)} active tasks to complete"
            )
            # Copy the set to avoid modification during iteration
            tasks_to_wait = list(self.active_tasks)
            logger.info(
                f"{self._log_prelude()} tasks to wait for: {[task.get_name() if hasattr(task, 'get_name') else str(task) for task in tasks_to_wait]}"
            )

            try:
                # Wait for tasks with a timeout of 30 seconds
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_wait, return_exceptions=True), timeout=30.0
                )
                logger.info(f"{self._log_prelude()} all active tasks completed")
            except TimeoutError:
                logger.info(
                    f"{self._log_prelude()} timeout waiting for tasks to complete. cancelling remaining tasks..."
                )
                # Cancel any remaining tasks
                for task in tasks_to_wait:
                    if not task.done():
                        logger.info(f"{self._log_prelude()} cancelling task: {task}")
                        task.cancel()
                # Wait a bit more for cancellation to complete
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks_to_wait, return_exceptions=True),
                        timeout=5.0,
                    )
                except TimeoutError:
                    logger.info(
                        f"{self._log_prelude()} some tasks could not be cancelled cleanly"
                    )
                logger.info(f"{self._log_prelude()} task cancellation completed")
            except Exception as e:
                logger.error(f"{self._log_prelude()} error during shutdown: {e}")
        else:
            logger.info(f"{self._log_prelude()} has no active tasks to wait for")

        logger.info(f"{self._log_prelude()} graceful shutdown completed")

    async def submit(self, message: MAILMessage) -> None:
        """
        Add a message to the priority queue
        Priority order:
        1. System message of any type
        2. User message of any type
        3. Agent interrupt, broadcast_complete
        4. Agent broadcast
        5. Agent request, response
        Within each category, messages are processed in FIFO order using a
        monotonically increasing sequence number to avoid dict comparisons.
        """
        recipients = (
            message["message"]["recipients"]  # type: ignore
            if "recipients" in message["message"]
            else [message["message"]["recipient"]]
        )
        logger.info(
            f'{self._log_prelude()} submitting message: "{message["message"]["sender"]}" -> "{[recipient["address"] for recipient in recipients]}" with subject "{message["message"]["subject"]}"'
        )

        priority = 0
        if message["message"]["sender"]["address_type"] == "system":
            priority = 1
        elif message["message"]["sender"]["address_type"] == "user":
            priority = 2
        elif message["message"]["sender"]["address_type"] == "agent":
            match message["msg_type"]:
                case "interrupt" | "broadcast_complete":
                    priority = 3
                case "broadcast":
                    priority = 4
                case "request" | "response":
                    priority = 5

        # Monotonic sequence to break ties for same priority
        self._message_seq += 1
        seq = self._message_seq

        await self.message_queue.put((priority, seq, message))

        return

    def _ensure_task_exists(self, task_id: str) -> None:
        """
        Ensure a task exists in swarm memory.
        """
        if task_id not in self.mail_tasks:
            self.mail_tasks[task_id] = MAILTask(task_id)

    async def _process_message(
        self,
        message: MAILMessage,
        action_override: ActionOverrideFunction | None = None,
    ) -> None:
        """
        The internal process for sending a message to the recipient agent(s)
        """
        # make sure this task_id exists in swarm memory
        task_id = message["message"]["task_id"]
        self._ensure_task_exists(task_id)

        # If interswarm messaging is enabled, try to route via interswarm router first
        if self.enable_interswarm and self.interswarm_router:
            # Check if any recipients are in interswarm format
            msg_content = message["message"]
            has_interswarm_recipients = False

            if "recipients" in msg_content:
                # if the message is a `broadcast_complete`, don't send it to the recipient agents
                # but DO append it to the agent history as tool calls (the actual broadcast)
                if message["msg_type"] == "broadcast_complete":
                    for agent in self.agents:
                        self.agent_histories[
                            AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=agent)
                        ].append(build_mail_xml(message))
                    return

                recipients_for_routing = msg_content["recipients"]  # type: ignore
                if recipients_for_routing == [MAIL_ALL_LOCAL_AGENTS]:  # type: ignore[comparison-overlap]
                    recipients_for_routing = [
                        create_agent_address(agent) for agent in self.agents.keys()
                    ]

                for recipient in recipients_for_routing:  # type: ignore[assignment]
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
                msg_content = message["message"]
                routing_info = (
                    msg_content.get("routing_info")
                    if isinstance(msg_content, dict)
                    else None
                )
                stream_requested = isinstance(routing_info, dict) and bool(
                    routing_info.get("stream")
                )
                ignore_stream_pings = isinstance(routing_info, dict) and bool(
                    routing_info.get("ignore_stream_pings")
                )

                async def forward_remote_event(
                    event_name: str, payload: str | None
                ) -> None:
                    if ignore_stream_pings and event_name == "ping":
                        return

                    try:
                        data = json.loads(payload) if payload else {}
                    except json.JSONDecodeError:
                        data = {"raw": payload}

                    if not isinstance(data, dict):
                        data = {"raw": data}

                    task_id = data.get("task_id")
                    if not isinstance(task_id, str):
                        return

                    self._ensure_task_exists(task_id)

                    sse = ServerSentEvent(data=data, event=event_name)

                    try:
                        self.mail_tasks[task_id].add_event(sse)
                    except Exception:
                        pass

                    self.new_events.append(sse)
                    try:
                        self._events_available.set()
                    except Exception:
                        pass

                response = await self.interswarm_router.route_message(
                    message,
                    stream_handler=forward_remote_event if stream_requested else None,
                    ignore_stream_pings=ignore_stream_pings,
                )
                logger.info(
                    f"{self._log_prelude()} received response from remote swarm for task '{response['message']['task_id']}', considering local handling"
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
                            complete_message = self._agent_task_complete(
                                task_id=task_id,
                                caller=self.entrypoint,
                                finish_message=msg.get(
                                    "body", "Task completed successfully"
                                ),
                            )

                            await self.submit(complete_message)

                            # Do not enqueue the raw response; we've completed the task
                            return

                except Exception as e:
                    logger.error(
                        f"{self._log_prelude()} error during interswarm auto-complete check: '{e}'"
                    )
                    self._submit_event(
                        "router_error",
                        message["message"]["task_id"],
                        f"error during interswarm auto-complete check: '{e}'",
                    )
                    await self.submit(
                        self._system_response(
                            task_id=message["message"]["task_id"],
                            recipient=message["message"]["sender"],
                            subject="::router_error::",
                            body=f"""An error occurred while auto-completing task '{task_id}' from interswarm response to '{recipient_addr}'.
The MAIL interswarm router encountered the following error: '{e}'
Use this information to decide how to complete your task.""",
                        )
                    )

                # Default behavior: enqueue response for local processing
                await self.submit(response)
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} error in interswarm routing: '{e}'"
                )

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
                        subject="::router_error::",
                        body=f"""Your message to '{message["message"]["sender"]["address"]}' was not delivered. 
The MAIL interswarm router encountered the following error: '{e}'
If your assigned task cannot be completed, inform your caller of this error and work together to come up with a solution.""",
                    )
                )
        else:
            logger.error(f"{self._log_prelude()} interswarm router not available")

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
                    subject="::router_error::",
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
        # if the message is a `broadcast_complete`, don't send it to the recipient agents
        # but DO append it to the agent history as tool calls (the actual broadcast)
        if message["msg_type"] == "broadcast_complete":
            for agent in self.agents:
                self.agent_histories[
                    AGENT_HISTORY_KEY.format(
                        task_id=message["message"]["task_id"], agent_name=agent
                    )
                ].append(build_mail_xml(message))
            return

        msg_content = message["message"]

        # Normalise recipients into a list of address strings (agent names or interswarm ids)
        raw_recipients: list[MAILAddress]
        if "recipients" in msg_content:
            raw_recipients = msg_content["recipients"]  # type: ignore
        else:
            raw_recipients = [msg_content["recipient"]]  # type: ignore[list-item]

        sender_address = message["message"]["sender"]["address"]

        recipient_addresses: list[str] = []
        for address in raw_recipients:
            addr_str = address["address"]
            if (
                addr_str == MAIL_ALL_LOCAL_AGENTS["address"]
                and address["address_type"] == "agent"
            ):
                recipient_addresses.extend(self.agents.keys())
            else:
                recipient_addresses.append(addr_str)

        # Drop duplicate addresses while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for addr in recipient_addresses:
            if addr not in seen:
                seen.add(addr)
                deduped.append(addr)

        # Prevent agents from broadcasting to themselves
        recipients = [addr for addr in deduped if addr != sender_address]

        for recipient in recipients:
            # Parse recipient address to get local agent name
            recipient_agent, recipient_swarm = parse_agent_address(recipient)

            # Only process if this is a local agent or no swarm specified
            if not recipient_swarm or recipient_swarm == self.swarm_name:
                if recipient_agent in self.agents:
                    self._send_message(recipient_agent, message, action_override)
                else:
                    logger.warning(
                        f"{self._log_prelude()} unknown local agent: '{recipient_agent}'"
                    )
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
                                recipient=create_agent_address(sender_agent),
                                subject="::improper_response_to_user::",
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
                                subject="::runtime_error::",
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
                                recipient=create_agent_address(sender_agent),
                                subject="::agent_error::",
                                body=f"""The agent '{recipient_agent}' is not known to this swarm.
Your directly reachable agents can be found in the tool definitions for `send_request` and `send_response`.""",
                            ),
                            action_override,
                        )
            else:
                logger.debug(
                    f"{self._log_prelude()} skipping remote agent '{recipient}' in local processing"
                )

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
            f'{self._log_prelude()} sending message: "{message["message"]["sender"]}" -> "{recipient}" with subject: "{message["message"]["subject"]}"'
        )
        self._submit_event(
            "new_message",
            message["message"]["task_id"],
            f"sending message:\n{build_mail_xml(message)['content']}",
            extra_data={
                "full_message": message,
            },
        )

        async def schedule(message: MAILMessage) -> None:
            """
            Schedule a message for processing.
            Agent functions are called here.
            """
            try:
                # prepare the message for agent input
                task_id = message["message"]["task_id"]
                tool_choice: str | dict[str, str] = "required"

                # get agent history for this task
                agent_history_key = AGENT_HISTORY_KEY.format(
                    task_id=task_id, agent_name=recipient
                )
                history = self.agent_histories[agent_history_key]

                if (
                    message["message"]["sender"]["address_type"] == "system"
                    and message["message"]["subject"] == "::maximum_steps_reached::"
                ):
                    tool_choice = {"type": "function", "name": "task_complete"}

                if not message["message"]["subject"].startswith(
                    "::action_complete_broadcast::"
                ):
                    incoming_message = build_mail_xml(message)
                    history.append(incoming_message)

                # agent function is called here
                agent_fn = self.agents[recipient].function
                _output_text, tool_calls = await agent_fn(history, tool_choice)  # type: ignore

                # append the agent's response to the history
                if tool_calls[0].completion:
                    history.append(tool_calls[0].completion)
                else:
                    history.extend(tool_calls[0].responses)

                breakpoint_calls = [
                    call
                    for call in tool_calls
                    if call.tool_name in self.breakpoint_tools
                ]
                if breakpoint_calls:
                    logger.info(
                        f"{self._log_prelude()} agent '{recipient}' used breakpoint tools '{', '.join([call.tool_name for call in breakpoint_calls])}'"
                    )
                    self._submit_event(
                        "breakpoint_tool_call",
                        task_id,
                        f"agent '{recipient}' used breakpoint tools '{', '.join([call.tool_name for call in breakpoint_calls])}'",
                    )
                    self.last_breakpoint_caller = recipient
                    self.last_breakpoint_tool_calls = breakpoint_calls
                    bp_dumps: list[dict[str, Any]] = []
                    if breakpoint_calls[0].completion:
                        bp_dumps.append(breakpoint_calls[0].completion)
                    else:
                        resps = breakpoint_calls[0].responses
                        for resp in resps:
                            if (
                                resp["type"] == "function_call"
                                and resp["name"] in self.breakpoint_tools
                            ):
                                bp_dumps.append(resp)
                    await self.submit(
                        self._system_broadcast(
                            task_id=task_id,
                            subject="::breakpoint_tool_call::",
                            body=f"{ujson.dumps(bp_dumps)}",
                            task_complete=True,
                        )
                    )
                    # Remove breakpoint tools from processing
                    tool_calls = [
                        tc
                        for tc in tool_calls
                        if tc.tool_name not in self.breakpoint_tools
                    ]

                # handle tool calls
                for call in tool_calls:
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
                                    self._tool_call_response(
                                        task_id=task_id,
                                        caller=recipient,
                                        tool_call=call,
                                        status="success",
                                        details="broadcast acknowledged",
                                    )
                                else:
                                    logger.warning(
                                        f"{self._log_prelude()} agent '{recipient}' used 'acknowledge_broadcast' on a '{message['msg_type']}'"
                                    )
                                    self._tool_call_response(
                                        task_id=task_id,
                                        caller=recipient,
                                        tool_call=call,
                                        status="error",
                                        details="improper use of `acknowledge_broadcast`",
                                    )
                                    await self.submit(
                                        self._system_response(
                                            task_id=task_id,
                                            recipient=create_agent_address(recipient),
                                            subject="::tool_call_error::",
                                            body=f"""The `acknowledge_broadcast` tool cannot be used in response to a message of type '{message["msg_type"]}'.
If your sender's message is a 'request', consider using `send_response` instead.
Otherwise, determine the best course of action to complete your task.""",
                                        )
                                    )
                            except Exception as e:
                                logger.error(
                                    f"{self._log_prelude()} error acknowledging broadcast for agent '{recipient}': '{e}'"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"error acknowledging broadcast: '{e}'",
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
                                        subject="::tool_call_error::",
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
                                f"{self._log_prelude()} agent '{recipient}' called 'ignore_broadcast'"
                            )
                            self._tool_call_response(
                                task_id=task_id,
                                caller=recipient,
                                tool_call=call,
                                status="success",
                                details="broadcast ignored",
                            )
                            self._submit_event(
                                "broadcast_ignored",
                                task_id,
                                f"agent '{recipient}' called 'ignore_broadcast'",
                            )
                            # No further action
                        case "await_message":
                            # only works if the message queue is not empty
                            if self.message_queue.empty():
                                logger.warning(
                                    f"{self._log_prelude()} agent '{recipient}' called 'await_message' but the message queue is empty"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details="message queue is empty",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"agent '{recipient}' called 'await_message' but the message queue is empty",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject="::tool_call_error::",
                                        body="""The tool call `await_message` was attempted but the message queue is empty.
In order to prevent frozen tasks, the `await_message` tool will only work if the message queue is not empty.
Consider sending a message to another agent to keep the task alive.""",
                                    )
                                )
                                return
                            wait_reason = call.tool_args.get("reason")
                            logger.info(
                                f"{self._log_prelude()} agent '{recipient}' called 'await_message'{f': {wait_reason}' if wait_reason else ''}",
                            )
                            details = "waiting for a new message"
                            if wait_reason:
                                details = f"{details} (reason: '{wait_reason}')"
                            self._tool_call_response(
                                task_id=task_id,
                                caller=recipient,
                                tool_call=call,
                                status="success",
                                details=details,
                            )
                            event_description = (
                                f"agent '{recipient}' is awaiting a new message"
                            )
                            if wait_reason:
                                event_description = (
                                    f"{event_description}: {wait_reason}"
                                )
                            self._submit_event(
                                "await_message",
                                task_id,
                                event_description,
                                extra_data={"reason": wait_reason}
                                if wait_reason
                                else {},
                            )
                            # No further action
                            return
                        case (
                            "send_request"
                            | "send_response"
                            | "send_interrupt"
                            | "send_broadcast"
                        ):
                            try:
                                await self.submit(
                                    convert_call_to_mail_message(
                                        call, recipient, task_id
                                    )
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="success",
                                    details="message sent",
                                )
                            except Exception as e:
                                logger.error(
                                    f"{self._log_prelude()} error sending message for agent '{recipient}': '{e}'"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"error sending message: '{e}'",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"error sending message for agent '{recipient}': '{e}'",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject="::tool_call_error::",
                                        body=f"""An error occurred while sending the message from '{message["message"]["sender"]["address"]}'.
Specifically, the MAIL runtime encountered the following error: '{e}'.
It is possible that the message sending tool is not implemented properly.
Use this information to decide how to complete your task.""",
                                    )
                                )
                        case "task_complete":
                            # Check if this completes a pending request
                            if task_id:
                                logger.info(
                                    f"{self._log_prelude()} task '{task_id}' completed, resolving pending request"
                                )

                                # Create a response message for the user
                                response_message = self._agent_task_complete(
                                    task_id=task_id,
                                    caller=recipient,
                                    finish_message=call.tool_args.get(
                                        "finish_message",
                                        "Task completed successfully",
                                    ),
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="success",
                                    details="task completed",
                                )

                                if not self._is_continuous:
                                    self._submit_event(
                                        "task_complete_call",
                                        task_id,
                                        f"agent '{recipient}' called 'task_complete', full response to follow",
                                    )
                                    await self.submit(response_message)
                                elif (
                                    self._is_continuous
                                    and task_id in self.pending_requests
                                ):
                                    self._submit_event(
                                        "task_complete_call",
                                        task_id,
                                        f"agent '{recipient}' called 'task_complete', full response to follow",
                                    )
                                    await self.submit(response_message)

                                elif self._is_continuous:
                                    logger.error(
                                        f"{self._log_prelude()} agent '{recipient}' called 'task_complete' but no pending request found"
                                    )
                                    self._tool_call_response(
                                        task_id=task_id,
                                        caller=recipient,
                                        tool_call=call,
                                        status="error",
                                        details="no pending request found",
                                    )
                                    self._submit_event(
                                        "task_error",
                                        task_id,
                                        f"agent '{recipient}' called 'task_complete' but no pending request found",
                                    )
                                    await self.submit(
                                        self._system_broadcast(
                                            task_id=task_id,
                                            subject="::tool_call_error::",
                                            body="""An agent called `task_complete` but the corresponding task was not found.
This should never happen; consider informing the MAIL developers of this issue if you see it.""",
                                            task_complete=True,
                                        )
                                    )
                        case "help":
                            try:
                                help_string = build_mail_help_string(
                                    name=recipient,
                                    swarm=self.swarm_name,
                                    get_summary=call.tool_args.get("get_summary", True),
                                    get_identity=call.tool_args.get(
                                        "get_identity", False
                                    ),
                                    get_tool_help=call.tool_args.get(
                                        "get_tool_help", []
                                    ),
                                    get_full_protocol=call.tool_args.get(
                                        "get_full_protocol", False
                                    ),
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="success",
                                    details="help string generated; will be sent to you in a subsequent prompt",
                                )
                                self._submit_event(
                                    "help_called",
                                    task_id,
                                    f"agent '{recipient}' called 'help'",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::help::",
                                        body=help_string,
                                        recipients=[create_agent_address(recipient)],
                                    )
                                )
                            except Exception as e:
                                logger.error(
                                    f"{self._log_prelude()} error calling help tool for agent '{recipient}': '{e}'"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"error calling help tool: '{e}'",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"error calling help tool for agent '{recipient}': '{e}'",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::tool_call_error::",
                                        body=f"""An error occurred while calling the help tool for agent '{recipient}'.
Specifically, the MAIL runtime encountered the following error: '{e}'.
This should never happen; consider informing the MAIL developers of this issue if you see it.""",
                                        task_complete=True,
                                    )
                                )
                                continue

                            continue

                        case _:
                            action_name = call.tool_name
                            action_caller = self.agents.get(recipient)

                            if action_caller is None:
                                logger.error(
                                    f"{self._log_prelude()} agent '{recipient}' not found"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details="agent not found",
                                )
                                self._submit_event(
                                    "action_error",
                                    task_id,
                                    f"agent '{recipient}' not found",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::tool_call_error::",
                                        body=f"""An agent called `{call.tool_name}` but the agent was not found.
This should never happen; consider informing the MAIL developers of this issue if you see it.""",
                                        task_complete=True,
                                    )
                                )
                                continue

                            action = self.actions.get(action_name)
                            if action is None:
                                logger.warning(
                                    f"{self._log_prelude()} action '{action_name}' not found"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details="action not found",
                                )
                                self._submit_event(
                                    "action_error",
                                    task_id,
                                    f"action '{action_name}' not found",
                                )
                                self._system_response(
                                    task_id=task_id,
                                    recipient=create_agent_address(recipient),
                                    subject="::action_error::",
                                    body=f"""The action '{action_name}' cannot be found in this swarm.""",
                                )
                                continue

                            if not action_caller.can_access_action(action_name):
                                logger.warning(
                                    f"{self._log_prelude()} agent '{action_caller}' cannot access action '{action_name}'"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details="agent cannot access action",
                                )
                                self._submit_event(
                                    "action_error",
                                    task_id,
                                    f"agent '{action_caller}' cannot access action '{action_name}'",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject="::action_error::",
                                        body=f"The action '{action_name}' is not available.",
                                    )
                                )
                                continue

                            logger.info(
                                f"{self._log_prelude()} agent '{recipient}' executing action tool: '{call.tool_name}'"
                            )
                            self._submit_event(
                                "action_call",
                                task_id,
                                f"agent '{recipient}' executing action tool: '{call.tool_name}'",
                            )
                            try:
                                # execute the action function
                                result_status, result_message = await action.execute(
                                    call,
                                    actions=self.actions,
                                    action_override=action_override,
                                )

                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status=result_status,
                                    details=result_message.get("content", ""),
                                )
                                self._submit_event(
                                    "action_complete",
                                    task_id,
                                    f"action complete (caller = '{recipient}'):\n'{result_message.get('content')}'",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::action_complete_broadcast::",
                                        body="",
                                        recipients=[create_agent_address(recipient)],
                                    )
                                )
                                continue
                            except Exception as e:
                                logger.error(
                                    f"{self._log_prelude()} error executing action tool '{call.tool_name}': '{e}'"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"failed to execute action tool: '{e}'",
                                )
                                self._submit_event(
                                    "action_error",
                                    task_id,
                                    f"action error (caller = '{recipient}', tool = '{call.tool_name}'):\n'{e}'",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::action_error::",
                                        body=f"""An error occurred while executing the action tool `{call.tool_name}`.
Specifically, the MAIL runtime encountered the following error: '{e}'.
It is possible that the action tool `{call.tool_name}` is not implemented properly.
Use this information to decide how to complete your task.""",
                                        task_complete=True,
                                        recipients=[create_agent_address(recipient)],
                                    )
                                )
                                continue

                self.agent_histories.setdefault(agent_history_key, [])
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} error scheduling message for agent '{recipient}': '{e}'"
                )
                self._tool_call_response(
                    task_id=task_id,
                    caller=recipient,
                    tool_call=call,
                    status="error",
                    details=f"failed to schedule message: '{e}'",
                )
                self._submit_event(
                    "agent_error",
                    task_id,
                    f"error scheduling message for agent '{recipient}': '{e}'",
                )
                await self.submit(
                    self._system_response(
                        task_id=task_id,
                        recipient=message["message"]["sender"],
                        subject="::agent_error::",
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

    def _agent_task_complete(
        self,
        task_id: str,
        caller: str,
        finish_message: str,
    ) -> MAILMessage:
        """
        Create a task complete message for an agent.
        """
        return MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILBroadcast(
                task_id=task_id,
                broadcast_id=str(uuid.uuid4()),
                sender=create_agent_address(caller),
                recipients=[create_agent_address("all")],
                subject="::task_complete::",
                body=finish_message,
                sender_swarm=self.swarm_name,
                recipient_swarms=[self.swarm_name],
                routing_info={},
            ),
            msg_type="broadcast_complete",
        )

    def _tool_call_response(
        self,
        task_id: str,
        caller: str,
        tool_call: AgentToolCall,
        status: Literal["success", "error"],
        details: str | None = None,
    ) -> None:
        """
        Create a tool call response message for a caller and append to its agent history.
        """
        agent_history_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=caller)

        status_str = "SUCCESS" if status == "success" else "ERROR"
        response_content = f"{status_str}: {details}" if details else status_str
        self.agent_histories[agent_history_key].append(
            tool_call.create_response_msg(response_content)
        )

        return

    def _submit_event(
        self,
        event: str,
        task_id: str,
        description: str,
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Submit an event to the event queue.
        """
        self._ensure_task_exists(task_id)

        if extra_data is None:
            extra_data = {}

        sse = ServerSentEvent(
            data={
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "description": description,
                "task_id": task_id,
                "extra_data": extra_data,
            },
            event=event,
        )
        self.new_events.append(sse)
        self.mail_tasks[task_id].add_event(sse)
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
        candidates: list[ServerSentEvent] = []
        try:
            candidates.extend(self.mail_tasks[task_id].events)
        except Exception:
            pass

        out: list[ServerSentEvent] = []
        for ev in candidates:
            try:
                if isinstance(ev.data, dict) and ev.data.get("task_id") == task_id:
                    out.append(ev)
            except Exception:
                continue
        return out

    def get_task_by_id(self, task_id: str) -> MAILTask | None:
        """
        Get a task by ID.
        """
        return self.mail_tasks.get(task_id)

    def get_response_message(self, task_id: str) -> MAILMessage | None:
        """
        Get the response message for a given task ID. Mostly used after streaming response events.
        """
        return self.response_messages.get(task_id, None)
