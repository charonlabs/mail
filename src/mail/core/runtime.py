# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Ryan Heaton

import asyncio
import copy
import datetime
import logging
import traceback
import uuid
from asyncio import PriorityQueue, Task
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any, Literal

import langsmith as ls
import rich
import tiktoken
import ujson
from litellm import aresponses
from sse_starlette import ServerSentEvent

from mail.db.utils import (
    create_agent_history,
    create_task,
    create_task_event,
    create_task_response,
    load_agent_histories,
    load_task_events,
    load_task_responses,
    load_tasks,
    update_task,
)
from mail.net import InterswarmRouter, SwarmRegistry
from mail.utils.context import get_model_ctx_len
from mail.utils.serialize import _REDACT_KEYS, _format_event_sections, _serialize_event
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
    MAILInterswarmMessage,
    MAILMessage,
    MAILRequest,
    MAILResponse,
    build_interswarm_mail_xml,
    build_mail_xml,
    create_agent_address,
    create_system_address,
    parse_agent_address,
)
from .tasks import MAILTask
from .tools import (
    AgentToolCall,
    convert_call_to_mail_message,
    convert_manual_step_call_to_mail_message,
    normalize_breakpoint_tool_call,
)

logger = logging.getLogger("mail.runtime")

AGENT_HISTORY_KEY = "{task_id}::{agent_name}"
_UNSET = object()


class _SSEPayload(dict):
    def __str__(self) -> str:
        return ujson.dumps(self)


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
        user_role: Literal["admin", "agent", "user"],
        swarm_name: str,
        entrypoint: str,
        swarm_registry: SwarmRegistry | None = None,
        enable_interswarm: bool = False,
        breakpoint_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        enable_db_agent_histories: bool = False,
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
        self.enable_db_agent_histories = enable_db_agent_histories
        # MAIL tasks in swarm memory
        self.mail_tasks: dict[str, MAILTask] = {}
        # asyncio tasks that are currently active
        self.active_tasks: set[Task[Any]] = set()
        self.shutdown_event = asyncio.Event()
        self.is_running = False
        self.pending_requests: dict[str, asyncio.Future[MAILMessage]] = {}
        self.user_id = user_id
        self.user_role = user_role
        self._steps_by_task: dict[str, int] = defaultdict(int)
        self._max_steps_by_task: dict[str, int | None] = {}
        # Per-task event notifier for streaming to avoid busy-waiting
        self._events_available_by_task: dict[str, asyncio.Event] = defaultdict(
            asyncio.Event
        )
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
        self.breakpoint_tools = list(breakpoint_tools or [])
        self._is_continuous = False
        self._is_manual = False
        # Message buffer for manual mode
        self.manual_message_buffer: dict[str, list[MAILMessage]] = defaultdict(list)
        self.manual_return_events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.manual_return_messages: dict[str, MAILMessage | None] = defaultdict(None)
        self.exclude_tools = list(exclude_tools or [])
        self.response_messages: dict[str, MAILMessage] = {}
        self.last_breakpoint_caller: dict[str, str] = {}
        self.last_breakpoint_tool_calls: dict[str, list[AgentToolCall]] = {}
        self.this_owner = f"{self.user_role}:{self.user_id}@{self.swarm_name}"
        # Track outstanding requests per task per agent for await_message
        # Structure: task_id -> sender_agent_name -> count of outstanding requests
        self.outstanding_requests: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

    def _log_prelude(self) -> str:
        """
        Build the string that will be prepended to all log messages.
        """
        return f"[[yellow]{self.user_role}[/yellow]:{self.user_id}@[green]{self.swarm_name}[/green]]"

    def _reset_step_counter(self, task_id: str) -> None:
        """
        Reset the step counter for a task (used to enforce per-task max_steps).
        """
        self._steps_by_task[task_id] = 0

    def _set_task_max_steps(self, task_id: str, max_steps: int | None) -> None:
        """
        Record a per-task max_steps override (None disables the limit).
        """
        self._max_steps_by_task[task_id] = max_steps

    def _normalize_max_steps(self, max_steps: Any) -> int | None:
        """
        Normalize a max_steps override into an int or None.
        """
        if max_steps is None:
            return None
        if isinstance(max_steps, int):
            return max_steps
        try:
            return int(max_steps)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_steps must be an int or null") from exc

    def _clear_task_step_state(self, task_id: str) -> None:
        """
        Clear step counters and overrides when a task completes.
        """
        self._steps_by_task.pop(task_id, None)
        self._max_steps_by_task.pop(task_id, None)

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

    async def load_agent_histories_from_db(self) -> None:
        """
        Load existing agent histories from the database.
        Only called when enable_db_agent_histories is True.
        """
        if not self.enable_db_agent_histories:
            return

        try:
            histories = await load_agent_histories(
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
            )
            # Merge loaded histories into agent_histories
            for key, history_list in histories.items():
                if key in self.agent_histories:
                    # Prepend loaded history to any existing history
                    self.agent_histories[key] = history_list + self.agent_histories[key]
                else:
                    self.agent_histories[key] = history_list

            logger.info(
                f"{self._log_prelude()} loaded {len(histories)} agent histories from database"
            )
        except Exception as e:
            logger.warning(
                f"{self._log_prelude()} failed to load agent histories from database: {e}"
            )

        # Also load tasks from DB
        await self.load_tasks_from_db()

    async def load_tasks_from_db(self) -> None:
        """
        Load existing tasks from the database.
        Only called when enable_db_agent_histories is True.
        """
        if not self.enable_db_agent_histories:
            return

        try:
            # Load task metadata
            task_records = await load_tasks(
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
            )

            for task_data in task_records:
                task_id = task_data["task_id"]
                if task_id in self.mail_tasks:
                    continue  # Don't overwrite existing tasks

                # Reconstruct task from DB data
                task = MAILTask.from_db_dict(task_data)
                self.mail_tasks[task_id] = task

                # Load events for this task
                events = await load_task_events(
                    task_id=task_id,
                    swarm_name=self.swarm_name,
                    caller_role=self.user_role,
                    caller_id=self.user_id,
                )
                for event_data in events:
                    task.add_event_from_db(event_data)

            # Load response messages
            responses = await load_task_responses(
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
            )
            for task_id, response in responses.items():
                self.response_messages[task_id] = response  # type: ignore

            logger.info(
                f"{self._log_prelude()} loaded {len(task_records)} tasks and {len(responses)} responses from database"
            )
        except Exception as e:
            logger.warning(
                f"{self._log_prelude()} failed to load tasks from database: {e}"
            )

    async def is_interswarm_running(self) -> bool:
        """
        Check if interswarm messaging is running.
        """
        if self.interswarm_router:
            return await self.interswarm_router.is_running()
        return False

    async def _handle_local_message(self, message: MAILInterswarmMessage) -> None:
        """
        Handle a message that should be processed locally.
        """
        await self._receive_interswarm_message(message)

    async def _notify_remote_task_complete(
        self,
        task_id: str,
        finish_message: str,
        caller: str,
    ) -> None:
        """
        Inform any participating remote swarms that the task has completed locally.
        """
        if not self.enable_interswarm or not self.interswarm_router:
            return

        task_state = self.mail_tasks.get(task_id)
        if task_state is None or not task_state.remote_swarms:
            return

        sender_address = create_agent_address(caller)

        for remote_swarm in task_state.remote_swarms:
            recipient = create_agent_address(f"{self.entrypoint}@{remote_swarm}")
            try:
                message = MAILMessage(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                    message=MAILResponse(
                        task_id=task_id,
                        request_id=str(uuid.uuid4()),
                        sender=sender_address,
                        recipient=recipient,
                        subject="::task_complete::",
                        body=finish_message,
                        sender_swarm=self.swarm_name,
                        recipient_swarm=remote_swarm,
                        routing_info={
                            "origin_swarm": self.swarm_name,
                            "remote_swarm": remote_swarm,
                        },
                    ),
                    msg_type="response",
                )
                await self._send_interswarm_message(message)
            except Exception as exc:
                logger.error(
                    f"{self._log_prelude()} failed to notify remote swarm '{remote_swarm}' of completion for task '{task_id}': '{exc}'"
                )

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
                self.mail_tasks[task_id].completed = False

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
                if (
                    task_id not in self.last_breakpoint_caller
                    or self.last_breakpoint_caller[task_id] is None
                ):
                    logger.error(
                        f"{self._log_prelude()} last breakpoint caller for task '{task_id}' is not set"
                    )
                    return self._system_broadcast(
                        task_id=task_id,
                        subject="::runtime_error::",
                        body="The last breakpoint caller is not set.",
                        task_complete=True,
                    )
                breakpoint_tool_caller = self.last_breakpoint_caller[task_id]
                breakpoint_tool_call_result = kwargs["breakpoint_tool_call_result"]

                self.mail_tasks[task_id].completed = False
                self.mail_tasks[task_id].is_running = True

                try:
                    result = await self._resume_task_from_breakpoint_tool_call(
                        task_id,
                        breakpoint_tool_caller,
                        breakpoint_tool_call_result,
                        action_override=action_override,
                    )
                finally:
                    self.mail_tasks[task_id].is_running = False

            case None:  # start a new task
                if task_id is None:
                    task_id = str(uuid.uuid4())
                await self._ensure_task_exists(task_id)

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
        logger.debug(
            f"{self._log_prelude()} _run_loop_for_task: starting for task_id={task_id}, "
            f"queue size={self.message_queue.qsize()}"
        )
        steps = 0
        while True:
            try:
                # Wait for either a message or shutdown signal
                logger.debug(
                    f"{self._log_prelude()} _run_loop_for_task: waiting for message, "
                    f"queue size={self.message_queue.qsize()}"
                )
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
                logger.debug(
                    f"{self._log_prelude()} _run_loop_for_task: got message from queue, "
                    f"priority={message_tuple[0]}, seq={message_tuple[1]}, "
                    f"remaining queue size={self.message_queue.qsize()}"
                )
                logger.info(
                    f"{self._log_prelude()} processing message with task ID '{message['message']['task_id']}': '{message['message']['subject']}'"
                )
                if message["msg_type"] == "broadcast_complete":
                    task_id_completed = message["message"].get("task_id")
                    if isinstance(task_id_completed, str):
                        self.response_messages[task_id_completed] = message
                        await self._ensure_task_exists(task_id_completed)
                        self.mail_tasks[task_id_completed].mark_complete()
                        await self.mail_tasks[task_id_completed].queue_stash(
                            self.message_queue
                        )
                        self._clear_task_step_state(task_id_completed)
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
                logger.error(f"{self._log_prelude()} error in run loop: {e}")
                self._submit_event(
                    "run_loop_error",
                    message["message"]["task_id"],
                    f"error in run loop: {e}",
                )
                return self._system_broadcast(
                    task_id=message["message"]["task_id"],
                    subject="::run_loop_error::",
                    body=f"An error occurred while running the MAIL system: {e}",
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
        logger.debug(
            f"{self._log_prelude()} _resume_task_from_breakpoint_tool_call: "
            f"task_id={task_id}, caller={breakpoint_tool_caller}, "
            f"result_type={type(breakpoint_tool_call_result).__name__}"
        )
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

        self.mail_tasks[task_id].resume()
        await self.mail_tasks[task_id].queue_load(self.message_queue)
        logger.debug(
            f"{self._log_prelude()} _resume_task_from_breakpoint_tool_call: "
            f"queue loaded, queue size={self.message_queue.qsize()}"
        )
        result_msgs: list[dict[str, Any]] = []
        if isinstance(breakpoint_tool_call_result, str):
            payload = ujson.loads(breakpoint_tool_call_result)
        else:
            payload = breakpoint_tool_call_result

        if task_id not in self.last_breakpoint_tool_calls:
            logger.error(
                f"{self._log_prelude()} last breakpoint tool calls for task '{task_id}' is not set"
            )
            return self._system_broadcast(
                task_id=task_id,
                subject="::runtime_error::",
                body="The last breakpoint tool calls is not set.",
                task_complete=True,
            )

        if isinstance(payload, list):
            for resp in payload:
                og_call = next(
                    (
                        call
                        for call in self.last_breakpoint_tool_calls[task_id]
                        if call.tool_call_id == resp["call_id"]
                    ),
                    None,
                )
                if og_call is not None:
                    result_msgs.append(og_call.create_response_msg(resp["content"]))
                    self._submit_event(
                        "breakpoint_action_complete",
                        task_id,
                        f"breakpoint action complete (caller = {breakpoint_tool_caller}):\n{resp['content']}",
                    )
        else:
            if len(self.last_breakpoint_tool_calls[task_id]) > 1:
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
                self.last_breakpoint_tool_calls[task_id][0].create_response_msg(
                    payload["content"]
                )
            )
            self._submit_event(
                "breakpoint_action_complete",
                task_id,
                f"breakpoint action complete (caller = {breakpoint_tool_caller}):\n{payload['content']}",
            )

        # append the breakpoint tool call result to the agent history
        logger.debug(
            f"{self._log_prelude()} _resume_task_from_breakpoint_tool_call: "
            f"appending {len(result_msgs)} result message(s) to history"
        )
        self.agent_histories[
            AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=breakpoint_tool_caller)
        ].extend(result_msgs)

        # send action complete broadcast to tool caller
        logger.debug(
            f"{self._log_prelude()} _resume_task_from_breakpoint_tool_call: "
            f"submitting ::action_complete_broadcast:: to {breakpoint_tool_caller}"
        )
        await self.submit(
            self._system_broadcast(
                task_id=task_id,
                subject="::action_complete_broadcast::",
                body="",
                recipients=[create_agent_address(breakpoint_tool_caller)],
            )
        )

        # resume the task
        logger.debug(
            f"{self._log_prelude()} _resume_task_from_breakpoint_tool_call: "
            f"entering _run_loop_for_task, queue size={self.message_queue.qsize()}"
        )
        self.mail_tasks[task_id].is_running = True
        try:
            result = await self._run_loop_for_task(task_id, action_override)
        finally:
            self.mail_tasks[task_id].is_running = False

        logger.debug(
            f"{self._log_prelude()} _resume_task_from_breakpoint_tool_call: "
            f"_run_loop_for_task completed"
        )
        return result

    async def run_continuous(
        self,
        max_steps: int | None = None,
        action_override: ActionOverrideFunction | None = None,
        mode: Literal["continuous", "manual"] = "continuous",
    ) -> None:
        """
        Run the MAIL system continuously, handling multiple requests.
        This method runs indefinitely until shutdown is requested.
        """
        self._is_continuous = True
        self._is_manual = mode == "manual"
        if self._is_manual:
            logger.info(
                f"{self._log_prelude()} starting manual MAIL operation for user '{self.user_id}'..."
            )
        else:
            logger.info(
                f"{self._log_prelude()} starting continuous MAIL operation for user '{self.user_id}'..."
            )
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
                logger.info(f"{self._log_prelude()} queue state: {self.message_queue}")
                logger.info(
                    f"{self._log_prelude()} processing message with task ID '{message['message']['task_id']}' and type '{message['msg_type']}' in continuous mode: '{message['message']['subject']}'"
                )
                task_id = message["message"]["task_id"]

                if message["msg_type"] == "broadcast_complete":
                    # Check if this completes a pending request
                    self.response_messages[task_id] = message
                    if isinstance(task_id, str):
                        await self._ensure_task_exists(task_id)
                        self.mail_tasks[task_id].mark_complete()
                        await self.mail_tasks[task_id].queue_stash(self.message_queue)
                        self._clear_task_step_state(task_id)
                    if isinstance(task_id, str) and task_id in self.pending_requests:
                        # Resolve the pending request
                        logger.info(
                            f"{self._log_prelude()} task '{task_id}' completed, resolving pending request"
                        )
                        future = self.pending_requests.pop(task_id)
                        future.set_result(message)
                        continue
                    else:
                        # Mark this message as done and continue processing
                        self.message_queue.task_done()
                        continue

                if (
                    not message["message"]["subject"].startswith("::")
                    and not message["message"]["sender"]["address_type"] == "system"
                ):
                    self._steps_by_task[task_id] += 1
                    max_steps_for_task = self._max_steps_by_task.get(
                        task_id, max_steps
                    )
                    if (
                        max_steps_for_task is not None
                        and self._steps_by_task[task_id] > max_steps_for_task
                    ):
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
                logger.error(f"{self._log_prelude()} error in continuous run loop: {e}")
                self._submit_event(
                    "run_loop_error",
                    "*",
                    f"continuous run loop error: {e}",
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
            max_steps_override = kwargs.pop("max_steps", _UNSET)
            if max_steps_override is not _UNSET:
                self._set_task_max_steps(
                    task_id, self._normalize_max_steps(max_steps_override)
                )
            match resume_from:
                case "user_response":
                    await self._submit_user_response(task_id, message, **kwargs)
                case "breakpoint_tool_call":
                    await self._submit_breakpoint_tool_call_result(task_id, **kwargs)
                case (
                    None
                ):  # start a new task (task_id should be provided in the message)
                    await self._ensure_task_exists(task_id)

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
                f"{self._log_prelude()} `submit_and_wait`: exception for task '{task_id}' with error: {e}"
            )
            self._submit_event("task_error", task_id, f"error for task: {e}")
            return self._system_broadcast(
                task_id=task_id,
                subject="::task_error::",
                body=f"The task encountered an error: {e}.",
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
            max_steps_override = kwargs.pop("max_steps", _UNSET)
            if max_steps_override is not _UNSET:
                self._set_task_max_steps(
                    task_id, self._normalize_max_steps(max_steps_override)
                )
            task_state = self.mail_tasks.get(task_id)
            if task_state is None and resume_from is None:
                await self._ensure_task_exists(task_id)
                task_state = self.mail_tasks.get(task_id)
            next_event_index = len(task_state.events) if task_state else 0

            match resume_from:
                case "user_response":
                    await self._submit_user_response(task_id, message, **kwargs)
                case "breakpoint_tool_call":
                    await self._submit_breakpoint_tool_call_result(task_id, **kwargs)
                case None:  # start a new task
                    await self.submit(message)

            # Stream events as they become available, emitting periodic heartbeats
            task_event = self._events_available_by_task[task_id]
            while not future.done():
                task_state = self.mail_tasks.get(task_id)
                task_events = task_state.events if task_state else []
                if next_event_index < len(task_events):
                    for ev in task_events[next_event_index:]:
                        payload = ev.data
                        if isinstance(payload, dict) and not isinstance(
                            payload, _SSEPayload
                        ):
                            payload = _SSEPayload(payload)
                        yield ServerSentEvent(
                            event=ev.event,
                            data=payload,
                            id=getattr(ev, "id", None),
                        )
                    next_event_index = len(task_events)
                    continue

                # Reset the event flag before waiting to avoid busy loops.
                task_event.clear()
                task_state = self.mail_tasks.get(task_id)
                task_events = task_state.events if task_state else []
                if next_event_index < len(task_events):
                    continue

                try:
                    # Wait up to 15s for new events; on timeout send a heartbeat
                    await asyncio.wait_for(task_event.wait(), timeout=15.0)
                except TimeoutError:
                    # Heartbeat to keep the connection alive
                    yield ServerSentEvent(
                        data=ujson.dumps({
                            "timestamp": datetime.datetime.now(
                                datetime.UTC
                            ).isoformat(),
                            "task_id": task_id,
                        }),
                        event="ping",
                    )
                    continue

            # Future completed; drain any remaining events before emitting final response
            task_state = self.mail_tasks.get(task_id)
            task_events = task_state.events if task_state else []
            if next_event_index < len(task_events):
                for ev in task_events[next_event_index:]:
                    payload = ev.data
                    if isinstance(payload, dict) and not isinstance(
                        payload, _SSEPayload
                    ):
                        payload = _SSEPayload(payload)
                    yield ServerSentEvent(
                        event=ev.event,
                        data=payload,
                        id=getattr(ev, "id", None),
                    )

            # Emit the final task_complete event with the response body
            try:
                response = future.result()
                yield ServerSentEvent(
                    data=_SSEPayload({
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                        "task_id": task_id,
                        "response": response["message"]["body"],
                    }),
                    event="task_complete",
                )
            except Exception as e:
                # If retrieving the response fails, still signal completion
                logger.error(
                    f"{self._log_prelude()} `submit_and_stream`: exception for task '{task_id}' with error: {e}"
                )
                yield ServerSentEvent(
                    data=_SSEPayload({
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                        "task_id": task_id,
                        "response": f"{e}",
                    }),
                    event="task_error",
                )

        except TimeoutError:
            self.pending_requests.pop(task_id, None)
            logger.error(
                f"{self._log_prelude()} `submit_and_stream`: timeout for task '{task_id}'"
            )
            yield ServerSentEvent(
                data=_SSEPayload({
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "task_id": task_id,
                    "response": "timeout",
                }),
                event="task_error",
            )

        except Exception as e:
            self.pending_requests.pop(task_id, None)
            logger.error(
                f"{self._log_prelude()} `submit_and_stream`: exception for task '{task_id}' with error: {e}"
            )
            yield ServerSentEvent(
                data=_SSEPayload({
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "task_id": task_id,
                    "response": f"{e}",
                }),
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

        self._reset_step_counter(task_id)
        self.mail_tasks[task_id].resume()
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

        self._reset_step_counter(task_id)
        self.mail_tasks[task_id].resume()
        await self.mail_tasks[task_id].queue_load(self.message_queue)

        # ensure valid kwargs
        REQUIRED_KWARGS: dict[str, type] = {
            "breakpoint_tool_call_result": str,
        }
        for kwarg, _type in REQUIRED_KWARGS.items():
            if kwarg not in kwargs:
                logger.error(
                    f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: required keyword argument '{kwarg}' not provided"
                )
                raise ValueError(f"required keyword argument '{kwarg}' not provided")
        breakpoint_tool_caller = kwargs.get("breakpoint_tool_caller", None)
        if breakpoint_tool_caller is None:
            if task_id not in self.last_breakpoint_caller:
                logger.error(
                    f"{self._log_prelude} `submmit_breakpoint_tool_call_result`: last breakpoint caller for task '{task_id}' is not set and no breakpoint tool caller was provided"
                )
                raise ValueError(
                    f"last breakpoint caller for task '{task_id}' is not set and no breakpoint tool caller was provided"
                )
            breakpoint_tool_caller = self.last_breakpoint_caller[task_id]
        breakpoint_tool_call_result = kwargs["breakpoint_tool_call_result"]

        if breakpoint_tool_caller is None:
            logger.error(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: breakpoint tool caller unknown"
            )
            raise ValueError(
                "breakpoint tool caller is required to resume from a breakpoint"
            )

        # ensure the agent exists already
        if breakpoint_tool_caller not in self.agents:
            logger.error(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: agent '{breakpoint_tool_caller}' not found"
            )
            raise ValueError(f"agent '{breakpoint_tool_caller}' not found")

        result_msgs: list[dict[str, Any]] = []
        if isinstance(breakpoint_tool_call_result, str):
            try:
                payload = ujson.loads(breakpoint_tool_call_result)
            except ValueError:
                payload = breakpoint_tool_call_result
        else:
            payload = breakpoint_tool_call_result

        logger.info(
            f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: payload: '{payload}'"
        )
        if task_id not in self.last_breakpoint_tool_calls:
            logger.error(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: last breakpoint tool calls for task '{task_id}' is not set"
            )
            raise ValueError(
                f"last breakpoint tool calls for task '{task_id}' is not set"
            )
        last_breakpoint_tool_calls = self.last_breakpoint_tool_calls[task_id]
        has_breakpoint_context = bool(last_breakpoint_tool_calls)

        if isinstance(payload, list) and has_breakpoint_context:
            logger.info(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: payload is a list and has breakpoint context"
            )
            logger.info(f"Current breakpoint tool calls: {last_breakpoint_tool_calls}")
            for resp in payload:
                og_call = next(
                    (
                        call
                        for call in last_breakpoint_tool_calls
                        if call.tool_call_id == resp["call_id"]
                    ),
                    None,
                )
                if og_call is not None:
                    result_msgs.append(og_call.create_response_msg(resp["content"]))
                    self._submit_event(
                        "breakpoint_action_complete",
                        task_id,
                        f"breakpoint action complete (caller = {breakpoint_tool_caller}):\n{resp['content']}",
                    )
                else:
                    logger.warning(
                        f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: no matching breakpoint tool call found for response: {resp}"
                    )
        else:
            if isinstance(payload, dict) and has_breakpoint_context:
                if len(last_breakpoint_tool_calls) > 1:
                    logger.error(
                        f"{self._log_prelude()} last breakpoint tool calls is a list but only one call response was provided"
                    )
                    raise ValueError(
                        "The last breakpoint tool calls is a list but only one call response was provided."
                    )
                result_msgs.append(
                    last_breakpoint_tool_calls[0].create_response_msg(
                        payload["content"]
                    )
                )
                self._submit_event(
                    "breakpoint_action_complete",
                    task_id,
                    f"breakpoint action complete (caller = {breakpoint_tool_caller}):\n{payload['content']}",
                )
            else:
                self._submit_event(
                    "breakpoint_action_complete",
                    task_id,
                    f"breakpoint action complete (caller = {breakpoint_tool_caller}):\n{payload}",
                )

        if isinstance(payload, list) and not has_breakpoint_context:
            logger.warning(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: received list payload but no breakpoint context is cached"
            )
        elif isinstance(payload, dict) and not has_breakpoint_context:
            logger.warning(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: received dict payload but no breakpoint context is cached"
            )
        elif has_breakpoint_context and not result_msgs:
            logger.warning(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: breakpoint context was available but no result messages were produced"
            )

        if (
            has_breakpoint_context
            and isinstance(payload, dict)
            and "content" not in payload
        ):
            logger.error(
                f"{self._log_prelude()} last breakpoint tool call payload missing 'content'"
            )
            raise ValueError("breakpoint tool call payload must include 'content'")

        # ensure result_msgs is not empty
        if not result_msgs:
            logger.warning(
                f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: no result messages were produced"
            )
            result_msgs.append(
                {
                    "role": "tool",
                    "content": str(payload),
                }
            )

        # append the breakpoint tool call result to the agent history
        self.agent_histories[
            AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=breakpoint_tool_caller)
        ].extend(result_msgs)

        await self.mail_tasks[task_id].queue_load(self.message_queue)

        # submit an action complete broadcast to the task
        logger.info(
            f"{self._log_prelude()} `submit_breakpoint_tool_call_result`: submitting action complete broadcast to the task"
        )
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
            f"{self._log_prelude()} submitting message: [yellow]{message['message']['sender']['address_type']}:{message['message']['sender']['address']}[/yellow] -> [yellow]{[f'{recipient["address_type"]}:{recipient["address"]}' for recipient in recipients]}[/yellow] with subject '{message['message']['subject']}'"
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

    async def _ensure_task_exists(
        self,
        task_id: str,
        task_owner: str | None = None,
        task_contributors: list[str] | None = None,
    ) -> None:
        """
        Ensure a task exists in swarm memory.
        """
        if task_id not in self.mail_tasks:
            if not task_owner:
                task_owner = self.this_owner
            if not task_contributors:
                task_contributors = [task_owner]
            else:
                task_contributors.append(task_owner)
            task = MAILTask(task_id, task_owner, task_contributors)
            self.mail_tasks[task_id] = task

            # Persist to DB if enabled
            if self.enable_db_agent_histories:
                await self._persist_task_to_db(task)

    async def _persist_task_to_db(self, task: MAILTask) -> None:
        """
        Persist a task to the database.
        """
        try:
            task_data = task.to_db_dict()
            await create_task(
                task_id=task_data["task_id"],
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
                task_owner=task_data["task_owner"],
                task_contributors=task_data["task_contributors"],
                remote_swarms=task_data["remote_swarms"],
                start_time=task_data["start_time"],
                is_running=task_data["is_running"],
                completed=task_data["completed"],
                title=task_data.get("title"),
            )
            logger.debug(
                f"{self._log_prelude()} persisted task '{task.task_id}' to database"
            )
        except Exception as e:
            logger.warning(
                f"{self._log_prelude()} failed to persist task '{task.task_id}' to database: {e}"
            )

    def _add_remote_task(
        self,
        task_id: str,
        task_owner: str,
        task_contributors: list[str],
    ) -> None:
        """
        Add a remote task to swarm memory.
        """
        if task_id in self.mail_tasks:
            logger.warning(f"a task with ID '{task_id}' already exists in swarm memory")
            raise ValueError(
                f"a task with ID '{task_id}' already exists in swarm memory"
            )
        self.mail_tasks[task_id] = MAILTask(task_id, task_owner, task_contributors)

    def _update_local_task(
        self,
        task_id: str,
        task_owner: str,
        task_contributors: list[str],
    ) -> None:
        """
        Update a local task in swarm memory.
        """
        if task_id not in self.mail_tasks:
            logger.warning(f"a task with ID '{task_id}' does not exist in swarm memory")
            raise ValueError(
                f"a task with ID '{task_id}' does not exist in swarm memory"
            )
        self.mail_tasks[task_id].task_owner = task_owner
        self.mail_tasks[task_id].task_contributors = task_contributors

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
        await self._ensure_task_exists(task_id)
        task_state = self.mail_tasks[task_id]

        if (
            task_state.completed
            and message["message"]["sender"]["address_type"] == "agent"
            and message["msg_type"] != "broadcast_complete"
        ):
            logger.info(
                f"{self._log_prelude()} ignoring message for completed task '{task_id}': '{message['message']['subject']}'"
            )
            try:
                self.message_queue.task_done()
            except Exception:
                pass
            return

        msg_content = message["message"]

        if "recipients" in msg_content and message["msg_type"] == "broadcast_complete":
            # Append broadcast completion to every agent history and stop
            for agent in self.agents:
                self.agent_histories[
                    AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=agent)
                ].append(build_mail_xml(message))
            task_state.mark_complete()
            await task_state.queue_stash(self.message_queue)
            return

        recipients_for_routing: list[MAILAddress] = []
        if "recipients" in msg_content:
            recipients_for_routing = msg_content["recipients"]  # type: ignore
            if recipients_for_routing == [MAIL_ALL_LOCAL_AGENTS]:  # type: ignore[comparison-overlap]
                recipients_for_routing = [
                    create_agent_address(agent) for agent in self.agents.keys()
                ]
        elif "recipient" in msg_content:
            recipients_for_routing = [msg_content["recipient"]]

        sender_info = msg_content.get("sender")
        disallowed_targets = self._find_disallowed_comm_targets(
            sender_info if isinstance(sender_info, dict) else None,
            recipients_for_routing,
            message["msg_type"],
        )
        if disallowed_targets:
            sender_label = (
                sender_info.get("address")
                if isinstance(sender_info, dict)
                else "unknown"
            )
            logger.warning(
                f"{self._log_prelude()} agent '{sender_label}' attempted to message targets outside comm_targets: {', '.join(disallowed_targets)}"
            )
            targets_str = ", ".join(disallowed_targets)
            body = (
                "Your message was not delivered because the following recipients "
                f"are not in your comm_targets: {targets_str}. "
                "Update the swarm configuration or choose an allowed recipient."
            )
            self._submit_event(
                "agent_error",
                task_id,
                f"agent attempted to contact disallowed recipients: {targets_str}",
            )
            if isinstance(sender_info, dict):
                await self.submit(
                    self._system_response(
                        task_id=task_id,
                        recipient=sender_info,  # type: ignore[arg-type]
                        subject="::invalid_recipient::",
                        body=body,
                    )
                )
            try:
                self.message_queue.task_done()
            except Exception:
                pass
            return

        if self.enable_interswarm and self.interswarm_router and recipients_for_routing:
            has_interswarm_recipients = False
            for recipient in recipients_for_routing:
                _, recipient_swarm = parse_agent_address(recipient["address"])
                if recipient_swarm and recipient_swarm != self.swarm_name:
                    has_interswarm_recipients = True
                    break

            if has_interswarm_recipients:
                asyncio.create_task(self._send_interswarm_message(message))
                try:
                    self.message_queue.task_done()
                except Exception:
                    pass
                return

        # Fall back to local processing
        await self._process_local_message(message, action_override)

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

    async def _receive_interswarm_message(
        self,
        message: MAILInterswarmMessage,
    ) -> None:
        """
        Receive a message from a remote swarm and route it to the appropriate local agent.
        """
        payload = message["payload"]
        task_id = payload["task_id"]
        recipients = payload.get("recipients") or [payload.get("recipient")]
        task_owner = message["task_owner"]
        task_contributors = message["task_contributors"]

        logger.debug(
            f"{self._log_prelude()} receiving interswarm message for task '{task_id}' with contributors: {task_contributors}"
        )

        assert isinstance(recipients, list)
        for recipient in recipients:
            assert isinstance(recipient, dict)
            assert "address" in recipient
            assert "address_type" in recipient
            recipient_agent, recipient_swarm = parse_agent_address(recipient["address"])
            if recipient_swarm != self.swarm_name:
                logger.debug(
                    f"{self._log_prelude()} skipping remote agent '{recipient_agent}' in interswarm message"
                )
                continue
            if recipient_agent not in self.agents:
                logger.warning(
                    f"{self._log_prelude()} unknown local agent: '{recipient_agent}'"
                )
                raise ValueError(f"unknown local agent: '{recipient_agent}'")

        # direction = forward
        if self.this_owner not in task_contributors:
            if task_id in self.mail_tasks:
                logger.warning(
                    f"a task with ID '{task_id}' already exists in swarm memory"
                )
                raise ValueError(
                    f"a task with ID '{task_id}' already exists in swarm memory"
                )
            self._add_remote_task(task_id, task_owner, task_contributors)
        # direction = back
        else:
            if task_id not in self.mail_tasks:
                logger.warning(
                    f"a task with ID '{task_id}' does not exist in swarm memory"
                )
                raise ValueError(
                    f"a task with ID '{task_id}' does not exist in swarm memory"
                )
            if self.mail_tasks[task_id].task_owner != task_owner:
                logger.warning(
                    f"task owner mismatch: expected '{self.mail_tasks[task_id].task_owner}', got '{task_owner}'"
                )
                raise ValueError(
                    f"task owner mismatch: expected '{self.mail_tasks[task_id].task_owner}', got '{task_owner}'"
                )
            # update task contributors in swarm memory
            self._update_local_task(task_id, task_owner, task_contributors)

        try:
            await self.submit(self._convert_interswarm_message_to_local(message))
            self._submit_event(
                "interswarm_message_received",
                task_id,
                f"received interswarm message from swarm {message['source_swarm']}",
            )
        except Exception as e:
            logger.error(
                f"{self._log_prelude()} error receiving interswarm message: {e}"
            )
            self._submit_event(
                "interswarm_message_error",
                task_id,
                f"error receiving interswarm message: {e}",
            )
            raise ValueError(f"error receiving interswarm message: {e}")

    async def _send_interswarm_message(
        self,
        message: MAILMessage,
    ) -> None:
        """
        Send a message to a remote swarm via the interswarm router.
        """
        # append this instance to the contributors list, if not already present
        if (
            self.this_owner
            not in self.mail_tasks[message["message"]["task_id"]].task_contributors
        ):
            self.mail_tasks[message["message"]["task_id"]].task_contributors.append(
                self.this_owner
            )

        task_id = message["message"]["task_id"]
        task_owner = self.mail_tasks[task_id].task_owner
        task_contributors = self.mail_tasks[task_id].task_contributors

        if self.interswarm_router is None:
            logger.error(f"{self._log_prelude()} interswarm router not available")
            raise ValueError("interswarm router not available")

        interswarm_message = self.interswarm_router.convert_local_message_to_interswarm(
            message,
            task_owner,
            task_contributors,
        )

        target_contributor = None
        for contributor in task_contributors:
            if contributor.split("@")[1] == interswarm_message["target_swarm"]:
                target_contributor = contributor
                break
        # direction = forward
        if target_contributor is None:
            try:
                await self.interswarm_router.send_interswarm_message_forward(
                    interswarm_message
                )
                self._submit_event(
                    "interswarm_message_sent",
                    task_id,
                    f"sent interswarm message forward to swarm {interswarm_message['target_swarm']}:\n{build_interswarm_mail_xml(interswarm_message)['content']}",
                )
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} runtime failed to send interswarm message forward: {e}"
                )
                self._submit_event(
                    "interswarm_message_error",
                    task_id,
                    f"error sending interswarm message forward: {e}",
                )
                raise ValueError(
                    f"runtime failed to send interswarm message forward: {e}"
                )
        # direction = back
        else:
            try:
                await self.interswarm_router.send_interswarm_message_back(
                    interswarm_message
                )
                self._submit_event(
                    "interswarm_message_sent",
                    task_id,
                    f"sent interswarm message back to swarm {interswarm_message['target_swarm']}:\n{build_interswarm_mail_xml(interswarm_message)['content']}",
                )
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} runtime failed to send interswarm message back: {e}"
                )
                self._submit_event(
                    "interswarm_message_error",
                    task_id,
                    f"error sending interswarm message back: {e}",
                )
                raise ValueError(f"runtime failed to send interswarm message back: {e}")

    def _find_disallowed_comm_targets(
        self,
        sender: MAILAddress | None,
        recipients: list[MAILAddress] | None,
        msg_type: str,
    ) -> list[str]:
        """
        Determine which recipients are not reachable for the sender based on comm_targets.
        """
        if (
            sender is None
            or recipients is None
            or msg_type in {"broadcast", "broadcast_complete"}
        ):
            return []
        if sender.get("address_type") != "agent":
            return []

        sender_agent, sender_swarm = parse_agent_address(sender["address"])
        if sender_swarm and sender_swarm != self.swarm_name:
            # Enforce comm_targets only for local agents
            return []

        agent_core = self.agents.get(sender_agent)
        if agent_core is None:
            return []

        allowed_targets = set(agent_core.comm_targets)
        disallowed: list[str] = []
        for recipient in recipients:
            if recipient.get("address_type") != "agent":
                continue
            recipient_address = recipient.get("address")
            if recipient_address in {None, MAIL_ALL_LOCAL_AGENTS["address"]}:
                continue
            if recipient_address not in allowed_targets:
                assert isinstance(recipient_address, str)
                disallowed.append(recipient_address)

        return disallowed

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

        # Prevent agents from broadcasting to themselves (but allow system messages
        # to agents even if the swarm name matches the agent name)
        sender_type = message["message"]["sender"]["address_type"]
        if sender_type == "system":
            recipients = deduped
        else:
            recipients = [addr for addr in deduped if addr != sender_address]

        for recipient in recipients:
            # Parse recipient address to get local agent name
            recipient_agent, recipient_swarm = parse_agent_address(recipient)

            # Only process if this is a local agent or no swarm specified
            if not recipient_swarm or recipient_swarm == self.swarm_name:
                sender_agent = message["message"]["sender"]
                if recipient_agent in self.agents:
                    if (
                        not self._is_manual
                        or message["message"]["sender"]["address_type"] == "system"
                    ):
                        self._send_message(recipient_agent, message, action_override)
                    else:
                        key = AGENT_HISTORY_KEY.format(
                            task_id=message["message"]["task_id"],
                            agent_name=recipient_agent,
                        )
                        self.manual_message_buffer[key].append(message)
                        logger.info(
                            f"{self._log_prelude()} added message to manual message buffer for agent '{recipient_agent}'"
                        )
                else:
                    logger.warning(
                        f"{self._log_prelude()} unknown local agent: '{recipient_agent}'"
                    )

                    # if the recipient is actually the user, indicate that
                    if recipient_agent == self.user_id:
                        self._submit_event(
                            "agent_error",
                            message["message"]["task_id"],
                            f"agent {message['message']['sender']['address']} attempted to send a message to the user ({self.user_id})",
                        )
                        self._send_message(
                            sender_agent["address"],
                            self._system_response(
                                task_id=message["message"]["task_id"],
                                recipient=create_agent_address(sender_agent["address"]),
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
                            f"agent {recipient_agent} is the swarm name; message from {message['message']['sender']['address']} cannot be delivered to it",
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
                            f"agent {recipient_agent} is unknown; message from {message['message']['sender']['address']} cannot be delivered to it",
                        )
                        self._send_message(
                            sender_agent["address"],
                            self._system_response(
                                task_id=message["message"]["task_id"],
                                recipient=create_agent_address(sender_agent["address"]),
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

    async def _manual_step(
        self,
        task_id: str,
        target: str,
        response_targets: list[str] | None = None,
        response_type: Literal["broadcast", "response", "request"] = "broadcast",
        payload: str | None = None,
        dynamic_ctx_ratio: float = 0.0,
        _llm: str | None = None,
        _system: str | None = None,
    ) -> MAILMessage:
        """
        Manually step a target agent and return the response message.
        """
        if not response_type == "broadcast" and response_targets is None:
            raise ValueError(
                "response_targets must be provided for non-broadcast response types"
            )
        response_targets = response_targets or ["all"]
        while not self.message_queue.empty():
            await asyncio.sleep(0.1)
        if target not in self.agents:
            logger.warning(f"{self._log_prelude()} unknown agent: '{target}'")
            raise ValueError(f"unknown agent target: '{target}'")
        if response_targets is not None:
            for response_target in response_targets:
                if (
                    response_target not in self.agents
                    and not response_target == MAIL_ALL_LOCAL_AGENTS["address"]
                ):
                    logger.warning(
                        f"{self._log_prelude()} unknown agent: '{response_target}'"
                    )
                    raise ValueError(
                        f"unknown agent response target: '{response_target}'"
                    )
        buffer_key = AGENT_HISTORY_KEY.format(task_id=task_id, agent_name=target)
        self.manual_return_events[buffer_key].clear()
        self.manual_return_messages[buffer_key] = None
        buffer = self.manual_message_buffer.get(buffer_key, [])
        body = ""
        for message in buffer:
            public_message = False
            private_group = False
            if "recipients" in message["message"]:
                if (
                    message["message"]["recipients"][0]["address"]  # type: ignore
                    == MAIL_ALL_LOCAL_AGENTS["address"]
                ):
                    body += "<public_message>\n"
                    public_message = True
                else:
                    body += "<private_message>\n"
                    private_group = True
            else:
                body += "<private_message>\n"
            body += f"<from>{message['message']['sender']['address']}</from>\n"
            if private_group:
                to = [
                    address["address"]
                    for address in message["message"]["recipients"]  # type: ignore
                ]
                body += f"<to>{', '.join(to)}</to>\n"
            body += f"{message['message']['body']}\n"
            if public_message:
                body += "</public_message>\n\n\n"
            else:
                body += "</private_message>\n\n\n"

        body += payload or ""
        body = body.rstrip()

        message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILRequest(
                task_id=task_id,
                request_id=str(uuid.uuid4()),
                sender=create_system_address("system"),
                recipient=create_agent_address(target),
                subject="::manual_step::",
                body=body,
                sender_swarm=None,
                recipient_swarm=None,
                routing_info={
                    "manual_response_type": response_type,
                    "manual_response_targets": response_targets,
                },
            ),
            msg_type="buffered",
        )
        self.manual_message_buffer[buffer_key].clear()

        self._send_message(target, message, None, dynamic_ctx_ratio, _llm, _system)
        await self.manual_return_events[buffer_key].wait()
        if self.manual_return_messages[buffer_key] is None:
            raise RuntimeError(
                f"no return message for agent '{target}' for task '{task_id}'"
            )
        return self.manual_return_messages[buffer_key]  # type: ignore

    def _send_message(
        self,
        recipient: str,
        message: MAILMessage,
        action_override: ActionOverrideFunction | None = None,
        dynamic_ctx_ratio: float = 0.0,
        _llm: str | None = None,
        _system: str | None = None,
    ) -> None:
        """
        Send a message to a recipient.
        """
        logger.info(
            f"{self._log_prelude()} sending message: [yellow]{message['message']['sender']['address_type']}:{message['message']['sender']['address']}[/yellow] -> [yellow]agent:{recipient}[/yellow] with subject: '{message['message']['subject']}'"
        )
        if not message["message"]["subject"].startswith(
            "::action_complete_broadcast::"
        ):
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
                tool_choice: str | dict[str, str] = (
                    "required" if not self._is_manual else "auto"
                )
                routing_info = message["message"].get("routing_info", {})

                # get agent history for this task
                agent_history_key = AGENT_HISTORY_KEY.format(
                    task_id=task_id, agent_name=recipient
                )
                history = self.agent_histories[agent_history_key]

                if (
                    message["message"]["sender"]["address_type"] == "system"
                    and message["message"]["subject"] == "::maximum_steps_reached::"
                    and not self._is_manual
                ):
                    tool_choice = {"type": "function", "name": "task_complete"}

                if not message["message"]["subject"].startswith(
                    "::action_complete_broadcast::"
                ):
                    if not message["msg_type"] == "buffered":
                        incoming_message = build_mail_xml(message)
                        history.append(incoming_message)
                    else:
                        history.append(
                            {"role": "user", "content": message["message"]["body"]}
                        )

                if dynamic_ctx_ratio > 0.0 and _llm is not None:
                    history = await self._compress_context(
                        self.agents[recipient],
                        _llm,
                        _system,
                        dynamic_ctx_ratio,
                        history,
                    )

                # agent function is called here
                agent_fn = self.agents[recipient].function
                _output_text, tool_calls = await agent_fn(history, tool_choice)  # type: ignore

                # append the agent's response to the history
                if tool_calls[0].completion:
                    history.append(tool_calls[0].completion)
                else:
                    history.extend(tool_calls[0].responses)

                # Emit tool_call events for all calls (before any mutations)
                # Track last call with reasoning for reasoning_ref
                last_reasoning_call_id: str | None = None
                for call in tool_calls:
                    if call.reasoning:
                        self._emit_tool_call_event(task_id, recipient, call)
                        last_reasoning_call_id = call.tool_call_id
                    else:
                        self._emit_tool_call_event(
                            task_id, recipient, call, reasoning_ref=last_reasoning_call_id
                        )

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
                        f"agent {recipient} used breakpoint tools {', '.join([call.tool_name for call in breakpoint_calls])} with args: {', '.join([ujson.dumps(call.tool_args) for call in breakpoint_calls])}",
                    )
                    self.last_breakpoint_caller[task_id] = recipient
                    self.last_breakpoint_tool_calls[task_id] = breakpoint_calls
                    bp_dumps: list[dict[str, Any]] = []
                    for call in breakpoint_calls:
                        raw_block: dict[str, Any] | None = None
                        if call.completion:
                            completion = call.completion
                            content = completion.get("content", [])
                            for block in content:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "tool_use"
                                    and block.get("id") == call.tool_call_id
                                ):
                                    raw_block = block
                                    break
                        else:
                            for resp in call.responses:
                                if (
                                    isinstance(resp, dict)
                                    and resp.get("type") == "function_call"
                                    and resp.get("call_id") == call.tool_call_id
                                ):
                                    raw_block = resp
                                    break
                        bp_dumps.append(
                            normalize_breakpoint_tool_call(call, raw_block)
                        )
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
                has_action_completed = False
                action_errors: list[tuple[str, Exception]] = []
                for call in tool_calls:
                    match call.tool_name:
                        case "text_output":
                            logger.info(
                                f"{self._log_prelude()} agent '{recipient}' sent raw text output with content: '{call.tool_args['content']}'"
                            )
                            call.tool_args["target"] = message["message"]["sender"][
                                "address"
                            ]
                            assert routing_info is not None
                            res_type = routing_info.get(
                                "manual_response_type", "broadcast"
                            )
                            res_targets = routing_info.get(
                                "manual_response_targets", ["all"]
                            )
                            outgoing_message = convert_manual_step_call_to_mail_message(
                                call, recipient, task_id, res_targets, res_type
                            )
                            self.manual_return_messages[agent_history_key] = (
                                outgoing_message
                            )
                            await self.submit(outgoing_message)
                            self.manual_return_events[agent_history_key].set()
                        case "acknowledge_broadcast":
                            try:
                                # Only store if this was a broadcast; otherwise treat as no-op
                                if message["msg_type"] == "broadcast":
                                    # note = call.tool_args.get("note")
                                    # async with get_langmem_store() as store:
                                    #     manager = create_memory_store_manager(
                                    #         "anthropic:claude-sonnet-4-20250514",
                                    #         query_model="anthropic:claude-sonnet-4-20250514",
                                    #         query_limit=10,
                                    #         namespace=(f"{recipient}_memory",),
                                    #         store=store,
                                    #     )
                                    #     assistant_content = (
                                    #         f"<acknowledged broadcast/>\n{note}".strip()
                                    #         if note
                                    #         else "<acknowledged broadcast/>"
                                    #     )
                                    #     await manager.ainvoke(
                                    #         {
                                    #             "messages": [
                                    #                 {
                                    #                     "role": "user",
                                    #                     "content": incoming_message[
                                    #                         "content"
                                    #                     ],
                                    #                 },
                                    #                 {
                                    #                     "role": "assistant",
                                    #                     "content": assistant_content,
                                    #                 },
                                    #             ]
                                    #         }
                                    #     )
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
                                    f"{self._log_prelude()} error acknowledging broadcast for agent '{recipient}': {e}"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"error acknowledging broadcast: {e}",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"error acknowledging broadcast for agent {recipient}: {e}",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject="::tool_call_error::",
                                        body=f"""An error occurred while acknowledging the broadcast from '{message["message"]["sender"]["address"]}'.
Specifically, the MAIL runtime encountered the following error: {e}.
It is possible that the `acknowledge_broadcast` tool is not implemented properly.
Use this information to decide how to complete your task.""",
                                    )
                                )
                            # No outgoing message submission for acknowledge
                        case "ignore_broadcast":
                            # Explicitly ignore without storing or responding
                            logger.info(
                                f"{self._log_prelude()} agent {recipient} called ignore_broadcast"
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
                                f"agent {recipient} called ignore_broadcast",
                            )
                            # No further action
                        case "await_message":
                            # Allow await if there are outstanding requests OR messages in queue
                            outstanding = self.outstanding_requests[task_id][recipient]
                            queue_empty = self.message_queue.empty()
                            if queue_empty and outstanding == 0:
                                logger.warning(
                                    f"{self._log_prelude()} agent '{recipient}' called 'await_message' "
                                    f"but has no outstanding requests and message queue is empty"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details="no outstanding requests and message queue is empty",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"agent {recipient} called await_message but has no outstanding requests and message queue is empty",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject="::tool_call_error::",
                                        body="""The tool call `await_message` was attempted but you have no outstanding requests and the message queue is empty.
In order to prevent frozen tasks, `await_message` only works if you have sent requests that haven't been responded to yet, or if there are messages waiting in the queue.
Consider sending a request to another agent before calling `await_message`.""",
                                    )
                                )
                                return
                            logger.debug(
                                f"{self._log_prelude()} agent '{recipient}' awaiting "
                                f"(outstanding={outstanding}, queue_empty={queue_empty})"
                            )
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
                                outgoing_message = convert_call_to_mail_message(
                                    call, recipient, task_id
                                )
                                self._attach_interswarm_routing_metadata(
                                    task_id, message, outgoing_message, call
                                )
                                await self.submit(outgoing_message)
                                # Track outstanding requests for await_message
                                if call.tool_name == "send_request":
                                    # Sender is waiting for a response
                                    self.outstanding_requests[task_id][recipient] += 1
                                    logger.debug(
                                        f"{self._log_prelude()} agent '{recipient}' sent request, "
                                        f"outstanding={self.outstanding_requests[task_id][recipient]}"
                                    )
                                elif call.tool_name == "send_response":
                                    # Response received, decrement target's outstanding count
                                    target = call.tool_args.get("target", "")
                                    if self.outstanding_requests[task_id][target] > 0:
                                        self.outstanding_requests[task_id][target] -= 1
                                        logger.debug(
                                            f"{self._log_prelude()} agent '{recipient}' sent response to '{target}', "
                                            f"target outstanding={self.outstanding_requests[task_id][target]}"
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
                                    f"{self._log_prelude()} error sending message for agent '{recipient}': {e}"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"error sending message: {e}",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"error sending message for agent {recipient}: {e}",
                                )
                                await self.submit(
                                    self._system_response(
                                        task_id=task_id,
                                        recipient=create_agent_address(recipient),
                                        subject="::tool_call_error::",
                                        body=f"""An error occurred while sending the message from '{message["message"]["sender"]["address"]}'.
Specifically, the MAIL runtime encountered the following error: {e}.
It is possible that the message sending tool is not implemented properly.
Use this information to decide how to complete your task.""",
                                    )
                                )
                        case "task_complete":
                            if task_id:
                                await self._handle_task_complete_call(
                                    task_id, recipient, call
                                )
                            else:
                                logger.error(
                                    f"{self._log_prelude()} agent '{recipient}' called 'task_complete' but no task id was provided"
                                )
                            continue
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
                                    f"agent {recipient} called help",
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
                                    f"{self._log_prelude()} error calling help tool for agent '{recipient}': {e}"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"error calling help tool: {e}",
                                )
                                self._submit_event(
                                    "agent_error",
                                    task_id,
                                    f"error calling help tool for agent {recipient}: {e}",
                                )
                                await self.submit(
                                    self._system_broadcast(
                                        task_id=task_id,
                                        subject="::tool_call_error::",
                                        body=f"""An error occurred while calling the help tool for agent '{recipient}'.
Specifically, the MAIL runtime encountered the following error: {e}.
This should never happen; consider informing the MAIL developers of this issue if you see it.""",
                                        task_complete=True,
                                    )
                                )
                                continue

                            continue

                        case "web_search_call":
                            # Built-in OpenAI tool - already executed, just emit trace event
                            logger.info(
                                f"{self._log_prelude()} agent '{recipient}' used web_search: query='{call.tool_args.get('query', '')}'"
                            )
                            self._submit_event(
                                "builtin_tool_call",
                                task_id,
                                f"agent {recipient} used web_search with query: {call.tool_args.get('query', '')}",
                                extra_data={
                                    "tool_type": "web_search_call",
                                    "tool_args": call.tool_args,
                                },
                            )
                            # No execution needed - OpenAI already ran this
                            continue

                        case "code_interpreter_call":
                            # Built-in OpenAI tool - already executed, just emit trace event
                            code_preview = (call.tool_args.get("code", "") or "")[:100]
                            logger.info(
                                f"{self._log_prelude()} agent '{recipient}' used code_interpreter: code='{code_preview}...'"
                            )
                            self._submit_event(
                                "builtin_tool_call",
                                task_id,
                                f"agent {recipient} used code_interpreter",
                                extra_data={
                                    "tool_type": "code_interpreter_call",
                                    "tool_args": call.tool_args,
                                },
                            )
                            # No execution needed - OpenAI already ran this
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
                                    f"agent {recipient} not found",
                                )
                                has_action_completed = True
                                action_errors.append(
                                    (
                                        call.tool_name,
                                        Exception(f"""An agent called `{call.tool_name}` but the agent was not found.
    This should never happen; consider informing the MAIL developers of this issue if you see it."""),
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
                                    f"action {action_name} not found",
                                )
                                has_action_completed = True
                                action_errors.append(
                                    (
                                        call.tool_name,
                                        Exception(
                                            f"""The action '{action_name}' cannot be found in this swarm."""
                                        ),
                                    )
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
                                    f"agent {action_caller} cannot access action {action_name}",
                                )
                                has_action_completed = True
                                action_errors.append(
                                    (
                                        call.tool_name,
                                        Exception(
                                            f"""The action '{action_name}' is not available."""
                                        ),
                                    )
                                )
                                continue

                            logger.info(
                                f"{self._log_prelude()} agent '{recipient}' executing action tool: '{call.tool_name}'"
                            )
                            self._submit_event(
                                "action_call",
                                task_id,
                                f"agent {recipient} executing action tool: {call.tool_name} with args: {ujson.dumps(call.tool_args)}",
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
                                    f"action complete (caller = {recipient}):\n{result_message.get('content')}",
                                )
                                has_action_completed = True
                                continue
                            except Exception as e:
                                logger.error(
                                    f"{self._log_prelude()} error executing action tool '{call.tool_name}': {e}"
                                )
                                self._tool_call_response(
                                    task_id=task_id,
                                    caller=recipient,
                                    tool_call=call,
                                    status="error",
                                    details=f"failed to execute action tool: {e}",
                                )
                                self._submit_event(
                                    "action_error",
                                    task_id,
                                    f"action error (caller = {recipient}, tool = {call.tool_name}):\n{e}",
                                )
                                has_action_completed = True
                                action_errors.append(
                                    (
                                        call.tool_name,
                                        Exception(f"""An error occurred while executing the action tool `{call.tool_name}`.
Specifically, the MAIL runtime encountered the following error: {e}.
It is possible that the action tool `{call.tool_name}` is not implemented properly.
Use this information to decide how to complete your task."""),
                                    )
                                )
                                continue

                if len(action_errors) > 0:
                    error_msg = "\n".join(
                        [f"Error: {error[0]}\n{error[1]}" for error in action_errors]
                    )
                    await self.submit(
                        self._system_response(
                            task_id=task_id,
                            recipient=create_agent_address(recipient),
                            subject="::action_error::",
                            body=error_msg,
                        )
                    )
                elif has_action_completed:
                    await self.submit(
                        self._system_broadcast(
                            task_id=task_id,
                            subject="::action_complete::",
                            body="Action completed successfully",
                            recipients=[create_agent_address(recipient)],
                        )
                    )

                self.agent_histories.setdefault(agent_history_key, [])
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} error scheduling message for agent '{recipient}': {e}"
                )
                traceback.print_exc()
                self._tool_call_response(
                    task_id=task_id,
                    caller=recipient,
                    tool_call=call,
                    status="error",
                    details=f"failed to schedule message: {e}",
                )
                self._submit_event(
                    "agent_error",
                    task_id,
                    f"error scheduling message for agent {recipient}: {e}",
                )
                await self.submit(
                    self._system_response(
                        task_id=task_id,
                        recipient=message["message"]["sender"],
                        subject="::agent_error::",
                        body=f"""An error occurred while scheduling the message for agent '{recipient}'.
Specifically, the MAIL runtime encountered the following error: {e}.
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

    def _attach_interswarm_routing_metadata(
        self,
        task_id: str,
        source_message: MAILMessage,
        outgoing_message: MAILMessage,
        call: AgentToolCall,
    ) -> None:
        """
        Propagate remote routing metadata so subsequent interswarm messages reuse the
        original remote task identifier.
        """
        try:
            outgoing_content = outgoing_message["message"]
            routing_info = outgoing_content.get("routing_info")
            if not isinstance(routing_info, dict):
                routing_info = {}

            parent_message = source_message.get("message")
            parent_routing: dict[str, Any] | None = None
            if isinstance(parent_message, dict):
                candidate_routing = parent_message.get("routing_info")
                if isinstance(candidate_routing, dict):
                    parent_routing = candidate_routing

            remote_task_id: str | None = None
            remote_swarm: str | None = None
            if parent_routing is not None:
                remote_task_id = parent_routing.get("remote_task_id")
                remote_swarm = parent_routing.get("remote_swarm")

            target_addresses: set[str] = set()

            target_arg = call.tool_args.get("target")
            if isinstance(target_arg, str):
                target_addresses.add(target_arg)

            if not target_addresses and call.tool_name == "send_broadcast":
                # Broadcasts default to local swarm; nothing to attach.
                outgoing_content["routing_info"] = routing_info
                return

            remote_swarms: set[str] = set()
            for address in target_addresses:
                _, swarm = parse_agent_address(address)
                if swarm:
                    remote_swarms.add(swarm)

            task_state = self.mail_tasks.get(task_id)
            if task_state is not None:
                for r_swarm in remote_swarms:
                    task_state.add_remote_swarm(r_swarm)

            if remote_swarms:
                routing_info.setdefault("remote_swarm", next(iter(remote_swarms)))

            outgoing_content["routing_info"] = routing_info
        except Exception:
            # Routing hints are best-effort; avoid interrupting the agent loop if unavailable.
            pass

    def _normalize_interswarm_response(
        self,
        task_id: str | None,
        response: MAILMessage,
    ) -> MAILMessage:
        """
        Normalize an interswarm response so it can be processed by the local queue.
        Converts remote task_complete broadcasts into response messages targeting the
        local entrypoint.
        """
        normalised = copy.deepcopy(response)
        message = normalised.get("message")

        if isinstance(message, dict):
            if isinstance(task_id, str):
                message["task_id"] = task_id
            routing_info = message.get("routing_info")
            if not isinstance(routing_info, dict):
                routing_info = {}
            routing_info.setdefault("origin_swarm", message.get("sender_swarm"))
            message["routing_info"] = routing_info

        if (
            normalised["msg_type"] == "broadcast_complete"
            and isinstance(message, dict)
            and message.get("subject") == "::task_complete::"
        ):
            finish_body = message.get("body", "")
            sender = message.get("sender")
            sender_swarm = message.get("sender_swarm")

            recipient = create_agent_address(self.entrypoint)

            if task_id is None:
                raise ValueError(
                    "task_id is required for interswarm task complete messages"
                )

            normalised = self._system_response(
                task_id=task_id,
                subject="::interswarm_task_complete::",
                body=f"""The remote agent '{sender}@{sender_swarm}' has completed the task with this ID in their swarm.
The final response message is: '{finish_body}'""",
                recipient=recipient,
            )

        return normalised

    async def _compress_context(
        self,
        agent: AgentCore,
        llm: str,
        system: str | None,
        ratio: float,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Compress the context of a list of messages based on the dynamic context ratio.

        When context exceeds (ratio * model_context_length) tokens, older messages
        (excluding the system prompt and recent messages) are summarized into a
        single compressed context block.
        """
        if llm.startswith("openai/gpt-5") or llm.startswith("openai/o3"):
            tokenizer = tiktoken.get_encoding("o200k_base")
        else:
            tokenizer = tiktoken.get_encoding("cl100k_base")
        try:
            ctx_len = get_model_ctx_len(llm)
        except Exception:
            logger.warning("failed to get context length for agent")
            logger.error(traceback.format_exc())
            return messages

        def get_content_from_messages(msgs: list[dict[str, Any]]) -> str:
            """Extract text content from messages, handling both dict and object formats."""
            full_content = ""
            for item in msgs:
                # Handle both dict-style and object-style messages
                if isinstance(item, dict):
                    content = item.get("content")
                else:
                    content = getattr(item, "content", None)

                if content is None:
                    continue

                if isinstance(content, str):
                    full_content += content + "\n\n"
                elif hasattr(content, "text"):
                    full_content += content.text + "\n\n"
                elif isinstance(content, list):
                    # Handle list of content blocks (e.g., OpenAI responses format)
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            full_content += block["text"] + "\n\n"
                        elif hasattr(block, "text"):
                            full_content += block.text + "\n\n"
            return full_content

        if system is None:
            system = ""
        full_content = get_content_from_messages(messages)
        full_content = system + full_content
        tokens = tokenizer.encode(full_content)
        threshold = int(ctx_len * ratio)
        rich.print(
            f"Context: [{len(tokens)}/{ctx_len}] ({(len(tokens) / ctx_len) * 100:.2f}%)"
        )

        if len(tokens) > threshold:
            # Find a good cutoff point, keeping at least 4 recent messages
            rev_messages = messages[::-1]
            stop_idx = -1
            min_recent_to_keep = 4

            for idx, item in enumerate(rev_messages[min_recent_to_keep:]):
                # Check if this is a "boundary" message we can split at
                is_boundary = False
                if isinstance(item, dict):
                    role = item.get("role")
                    msg_type = item.get("type")
                    is_boundary = (
                        role in ("user", "assistant") or msg_type == "function_call"
                    )
                else:
                    is_boundary = hasattr(item, "role") or (
                        hasattr(item, "type") and item.type == "function_call"
                    )

                if is_boundary:
                    # Account for the slice offset when calculating original index
                    stop_idx = len(rev_messages) - (idx + min_recent_to_keep) - 1
                    break

            if stop_idx > 1:  # Ensure we have messages to compact (after system prompt)
                is_first_msg_sys = messages[0].get("role") == "system"
                msgs_to_compact = (
                    messages[1:stop_idx] if is_first_msg_sys else messages[0:stop_idx]
                )
                if not msgs_to_compact:
                    return messages

                compacted_content = get_content_from_messages(msgs_to_compact)
                if not compacted_content.strip():
                    return messages

                # Keep system prompt (messages[0]) and recent messages (messages[stop_idx:])
                if is_first_msg_sys:
                    messages = [messages[0]] + messages[stop_idx:]
                else:
                    messages = messages[stop_idx:]

                with ls.trace(
                    name="compress_context",
                    run_type="llm",
                    inputs={
                        "messages": messages,
                        "compacted_content": compacted_content,
                    },
                ) as rt:
                    res = await aresponses(
                        input="Compress the following messages of LLM context into a single, concise summary:\n"
                        + compacted_content,
                        instructions="Your goal is to compress given LLM context in a manner that is most likely to be useful to the LLM. Your summary will be inserted into the LLM's context in place of the original messages, so it should be concise while retaining important information.",
                        model="openai/gpt-5.1",
                        reasoning={"effort": "none"},
                    )
                    rt.end(outputs={"output": res})

                # Extract the summary and insert after system prompt
                for output in res.output:
                    summary_text = None
                    if isinstance(output, dict):
                        if output.get("type") == "message":
                            content_list = output.get("content", [])
                            if content_list and isinstance(content_list[0], dict):
                                summary_text = content_list[0].get("text", "")
                    elif hasattr(output, "type") and output.type == "message":
                        if hasattr(output, "content") and output.content:
                            summary_text = output.content[0].text

                    if summary_text:
                        # Insert after system prompt (position 1), not before it
                        messages.insert(
                            1 if is_first_msg_sys else 0,
                            {
                                "role": "user",
                                "content": f"[COMPRESSED CONTEXT FROM EARLIER IN CONVERSATION]\n\n{summary_text}",
                            },
                        )
                        break  # Only insert one summary

        return messages

    async def _handle_task_complete_call(
        self,
        task_id: str,
        caller: str,
        call: AgentToolCall,
    ) -> None:
        """
        Handle a task_complete tool invocation from an agent.
        Ensures the task is marked complete, the queue is stashed, and subsequent
        duplicate calls are treated as idempotent.
        """
        finish_message = call.tool_args.get(
            "finish_message", "Task completed successfully"
        )

        await self._ensure_task_exists(task_id)
        task_state = self.mail_tasks[task_id]

        if task_state.completed:
            logger.warning(
                f"{self._log_prelude()} agent '{caller}' called 'task_complete' for already completed task '{task_id}'"
            )
            self._tool_call_response(
                task_id=task_id,
                caller=caller,
                tool_call=call,
                status="success",
                details="task already completed",
            )
            self._submit_event(
                "task_complete_call_duplicate",
                task_id,
                f"agent {caller} called task_complete on already completed task",
            )
            return

        logger.info(
            f"{self._log_prelude()} task '{task_id}' completed by agent '{caller}'"
        )

        response_message = self._agent_task_complete(
            task_id=task_id,
            caller=caller,
            finish_message=finish_message,
        )

        self._tool_call_response(
            task_id=task_id,
            caller=caller,
            tool_call=call,
            status="success",
            details="task completed",
        )

        self._submit_event(
            "task_complete_call",
            task_id,
            f"agent {caller} called task_complete, full response to follow",
        )

        await task_state.queue_stash(self.message_queue)
        task_state.mark_complete()
        self._clear_task_step_state(task_id)

        # Clean up outstanding requests tracking for this task
        if task_id in self.outstanding_requests:
            del self.outstanding_requests[task_id]

        # Persist agent histories to the database if enabled
        await self._persist_agent_histories_to_db(task_id)

        # Persist task completion status and response to DB
        if self.enable_db_agent_histories:
            await self._persist_task_completion_to_db(task_id, response_message)

        self.response_messages[task_id] = response_message

        # Emit a synthetic new_message event so streaming clients receive the final content.
        # This must happen BEFORE resolving the pending request, otherwise the streaming
        # loop will exit before this event is emitted.
        self._submit_event(
            "new_message",
            task_id,
            f"task_complete response from {caller}:\n{build_mail_xml(response_message)['content']}",
            extra_data={"full_message": response_message},
        )

        await self._notify_remote_task_complete(task_id, finish_message, caller)
        await self.submit(response_message)

        # Resolve pending request if one exists - do this LAST so streaming clients
        # have a chance to receive the new_message event before the stream closes
        if task_id in self.pending_requests:
            logger.info(
                f"{self._log_prelude()} task '{task_id}' completed, resolving pending request"
            )
            future = self.pending_requests.pop(task_id)
            future.set_result(response_message)

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

    def _detect_tool_format(
        self, history: list[dict[str, Any]]
    ) -> Literal["completions", "responses"]:
        """
        Detect the tool format used in a history based on entry structure.
        Returns 'completions' if entries have 'role' key, 'responses' if they have 'type' key.
        Defaults to 'responses' if unable to determine.
        """
        for entry in history:
            if isinstance(entry, dict):
                if "role" in entry:
                    return "completions"
                if "type" in entry:
                    return "responses"
        return "responses"

    async def _persist_agent_histories_to_db(self, task_id: str) -> None:
        """
        Persist all agent histories for a given task to the database.
        Only called when enable_db_agent_histories is True.
        """
        if not self.enable_db_agent_histories:
            return

        for agent_name in self.agents:
            agent_history_key = AGENT_HISTORY_KEY.format(
                task_id=task_id, agent_name=agent_name
            )
            history = self.agent_histories.get(agent_history_key, [])

            if not history:
                continue

            tool_format = self._detect_tool_format(history)

            try:
                await create_agent_history(
                    swarm_name=self.swarm_name,
                    caller_role=self.user_role,
                    caller_id=self.user_id,
                    tool_format=tool_format,
                    task_id=task_id,
                    agent_name=agent_name,
                    history=history,
                )
                logger.info(
                    f"{self._log_prelude()} persisted history for agent '{agent_name}' (task '{task_id}', format '{tool_format}')"
                )
            except Exception as e:
                logger.error(
                    f"{self._log_prelude()} failed to persist history for agent '{agent_name}' (task '{task_id}'): {e}"
                )

    def _emit_tool_call_event(
        self,
        task_id: str,
        caller: str,
        call: AgentToolCall,
        reasoning_ref: str | None = None,
    ) -> None:
        """
        Emit a tool_call event for a tool call.

        Reasoning and preamble come from the AgentToolCall object fields (populated by factory).
        If the call has no reasoning but reasoning_ref is provided, include that instead.
        """
        extra_data: dict[str, Any] = {
            "tool_name": call.tool_name,
            "tool_args": call.tool_args,
            "tool_call_id": call.tool_call_id,
        }

        # Use reasoning from call object (populated by factory)
        # Filter empty/whitespace blocks and join with double newlines
        if call.reasoning:
            filtered = [r for r in call.reasoning if r and r.strip()]
            if filtered:
                extra_data["reasoning"] = "\n\n".join(filtered)
            elif reasoning_ref:
                # Had reasoning list but all blocks were empty/whitespace
                extra_data["reasoning_ref"] = reasoning_ref
        elif reasoning_ref:
            extra_data["reasoning_ref"] = reasoning_ref

        if call.preamble:
            extra_data["preamble"] = call.preamble

        self._submit_event(
            "tool_call",
            task_id,
            f"agent {caller} called {call.tool_name}",
            extra_data=extra_data,
        )

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
        # Ensure task exists in memory (sync check, DB persistence happens elsewhere)
        if task_id not in self.mail_tasks:
            task_owner = self.this_owner
            task = MAILTask(task_id, task_owner, [task_owner])
            self.mail_tasks[task_id] = task
            # Schedule DB persistence in background if enabled
            if self.enable_db_agent_histories:
                asyncio.create_task(self._persist_task_to_db(task))

        if extra_data is None:
            extra_data = {}

        # Pre-serialize to JSON to ensure proper formatting (sse_starlette may use str() instead)
        sse = ServerSentEvent(
            data=ujson.dumps({
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "description": description,
                "task_id": task_id,
                "extra_data": extra_data,
            }),
            event=event,
        )
        self.mail_tasks[task_id].add_event(sse)
        # Signal that new events are available for streaming (task-specific)
        try:
            self._events_available_by_task[task_id].set()
        except Exception:
            pass

        # Persist event to DB in background if enabled
        if self.enable_db_agent_histories:
            asyncio.create_task(self._persist_event_to_db(task_id, sse))

        return None

    async def _persist_event_to_db(self, task_id: str, sse: ServerSentEvent) -> None:
        """
        Persist an event to the database.
        """
        try:
            # Serialize event data to string if needed
            event_data = sse.data
            if event_data is not None and not isinstance(event_data, str):
                import json

                event_data = json.dumps(event_data)

            await create_task_event(
                task_id=task_id,
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
                event_type=sse.event,
                event_data=event_data,
                event_id=sse.id,
            )
        except Exception as e:
            logger.warning(
                f"{self._log_prelude()} failed to persist event for task '{task_id}': {e}"
            )

    async def _persist_task_completion_to_db(
        self, task_id: str, response_message: MAILMessage
    ) -> None:
        """
        Persist task completion status and response message to the database.
        """
        try:
            # Update task status
            await update_task(
                task_id=task_id,
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
                is_running=False,
                completed=True,
            )

            # Save response message
            await create_task_response(
                task_id=task_id,
                swarm_name=self.swarm_name,
                caller_role=self.user_role,
                caller_id=self.user_id,
                response=response_message,  # type: ignore
            )

            logger.info(
                f"{self._log_prelude()} persisted task completion for task '{task_id}'"
            )
        except Exception as e:
            logger.warning(
                f"{self._log_prelude()} failed to persist task completion for task '{task_id}': {e}"
            )

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
                payload = ev.data
                if isinstance(payload, str):
                    try:
                        payload = ujson.loads(payload)
                    except ValueError:
                        payload = None
                if isinstance(payload, dict) and payload.get("task_id") == task_id:
                    out.append(
                        ServerSentEvent(
                            event=ev.event,
                            data=payload,
                            id=getattr(ev, "id", None),
                        )
                    )
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
