import asyncio
import datetime
import logging
from typing import Any
import uuid
from asyncio import PriorityQueue, Task

from acp.executor import execute_action_tool
from acp.message import ACPBroadcast, ACPMessage, build_acp_xml, ACPResponse
from acp.tools import (
    ACP_TOOL_NAMES,
    action_complete_broadcast,
    convert_call_to_acp_message,
)
from acp.factories.action import ActionFunction
from acp.factories.base import AgentFunction

logger = logging.getLogger("acp")


class ACP:
    def __init__(
        self,
        agents: dict[str, AgentFunction],
        actions: dict[str, ActionFunction],
        user_token: str = None,
    ):
        self.message_queue: PriorityQueue[tuple[int, ACPMessage]] = PriorityQueue()
        self.response_queue: asyncio.Queue[tuple[str, ACPMessage]] = asyncio.Queue()
        self.agents = agents
        self.actions = actions
        self.agent_histories: dict[str, list[dict[str, Any]]] = {
            agent: [] for agent in agents
        }
        self.active_tasks: set[Task[Any]] = set()
        self.shutdown_event = asyncio.Event()
        self.response_to_user: ACPMessage | None = None
        self.is_running = False
        self.current_request_id: str | None = None
        self.pending_requests: dict[str, asyncio.Future[ACPMessage]] = {}
        self.user_token = user_token  # Track which user this ACP instance belongs to

    async def run(self) -> ACPMessage:
        """
        Run the ACP system until a task is complete or shutdown is requested.
        This method can be called multiple times for different requests.
        """
        if self.is_running:
            logger.warning(f"ACP is already running for user {self.user_token[:8] if self.user_token else 'unknown'}, cannot start another run")
            return self._system_shutdown_message("ACP already running")
        
        self.is_running = True
        self.response_to_user = None
        
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
                        logger.info(f"shutdown requested for user {self.user_token[:8] if self.user_token else 'unknown'}...")
                        self.response_to_user = self._system_shutdown_message(
                            "shutdown requested"
                        )
                        break

                    # Process the message
                    message_tuple = get_message_task.result()
                    message = message_tuple[1]
                    logger.info(f"Processing message for user {self.user_token[:8] if self.user_token else 'unknown'}: {message}")

                    if message["msg_type"] == "broadcast_complete":
                        # Mark this message as done before breaking
                        self.message_queue.task_done()
                        self.response_to_user = message
                        break

                    self._process_message(self.user_token, message)
                    # Note: task_done() is called by the schedule function for regular messages

                except asyncio.CancelledError:
                    logger.info(f"run loop cancelled for user {self.user_token[:8] if self.user_token else 'unknown'}, initiating shutdown...")
                    self.response_to_user = self._system_shutdown_message(
                        "run loop cancelled"
                    )
                    break
                except Exception as e:
                    logger.error(f"error in run loop for user {self.user_token[:8] if self.user_token else 'unknown'}: {e}")
                    self.response_to_user = self._system_shutdown_message(
                        f"error in run loop: {e}"
                    )
                    break
        finally:
            self.is_running = False
            return self.response_to_user  # type: ignore

    async def run_continuous(self) -> None:
        """
        Run the ACP system continuously, handling multiple requests.
        This method runs indefinitely until shutdown is requested.
        """
        user_id = self.user_token[:8] if self.user_token else 'unknown'
        logger.info(f"Starting continuous ACP operation for user {user_id}...")
        
        while not self.shutdown_event.is_set():
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
                    logger.info(f"shutdown requested in continuous mode for user {user_id}...")
                    break

                # Process the message
                message_tuple = get_message_task.result()
                message = message_tuple[1]
                logger.info(f"Processing message in continuous mode for user {user_id}: {message}")

                if message["msg_type"] == "broadcast_complete":
                    # Mark this message as done and continue processing
                    self.message_queue.task_done()
                    continue

                self._process_message(self.user_token, message)
                # Note: task_done() is called by the schedule function for regular messages

            except asyncio.CancelledError:
                logger.info(f"continuous run loop cancelled for user {user_id}...")
                break
            except Exception as e:
                logger.error(f"error in continuous run loop for user {user_id}: {e}")
                # Continue processing other messages instead of shutting down
                continue
        
        logger.info(f"Continuous ACP operation stopped for user {user_id}.")

    async def submit_and_wait(self, message: ACPMessage, timeout: float = 3600.0) -> ACPMessage:
        """
        Submit a message and wait for the response.
        This method is designed for handling individual requests in a persistent ACP instance.
        """
        request_id = message["message"]["request_id"]
        user_id = self.user_token[:8] if self.user_token else 'unknown'
        
        # Create a future to wait for the response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # Submit the message
            await self.submit(message)
            
            # Wait for the response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            # Remove the pending request
            self.pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {request_id} for user {user_id} timed out after {timeout} seconds")
        except Exception as e:
            # Remove the pending request
            self.pending_requests.pop(request_id, None)
            raise e

    async def shutdown(self) -> None:
        """Request a graceful shutdown of the ACP system."""
        user_id = self.user_token[:8] if self.user_token else 'unknown'
        logger.info(f"requesting shutdown for user {user_id}...")
        self.shutdown_event.set()

    async def _graceful_shutdown(self) -> None:
        """Perform graceful shutdown operations."""
        logger.info("starting graceful shutdown...")

        # Graceful shutdown: wait for all active tasks to complete
        if self.active_tasks:
            logger.info(
                f"waiting for {len(self.active_tasks)} active tasks to complete..."
            )
            # Copy the set to avoid modification during iteration
            tasks_to_wait = list(self.active_tasks)
            logger.info(
                f"tasks to wait for: {[task.get_name() if hasattr(task, 'get_name') else str(task) for task in tasks_to_wait]}"
            )

            try:
                # Wait for tasks with a timeout of 30 seconds
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_wait, return_exceptions=True), timeout=30.0
                )
                logger.info("all active tasks completed.")
            except TimeoutError:
                logger.info(
                    "timeout waiting for tasks to complete. cancelling remaining tasks..."
                )
                # Cancel any remaining tasks
                for task in tasks_to_wait:
                    if not task.done():
                        logger.info(f"cancelling task: {task}")
                        task.cancel()
                # Wait a bit more for cancellation to complete
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks_to_wait, return_exceptions=True),
                        timeout=5.0,
                    )
                except TimeoutError:
                    logger.info("some tasks could not be cancelled cleanly.")
                logger.info("task cancellation completed.")
            except Exception as e:
                logger.error(f"error during shutdown: {e}")
        else:
            logger.info("no active tasks to wait for.")

        logger.info("graceful shutdown completed.")

    async def submit(self, message: ACPMessage) -> None:
        """
        Add a message to the priority queue
        Priority order:
        1. Interrupt
        2. Broadcast
        3. Request/response
        Within each category, the priority is determined by the timestamp of the message
        """
        recipients = (
            message["message"]["recipients"]  # type: ignore
            if "recipients" in message["message"]
            else [message["message"]["recipient"]]
        )
        logger.info(
            f'submitting message: "{message["message"]["sender"]}" -> "{recipients}" with header "{message["message"]["header"]}"'
        )

        priority = 0
        match message["msg_type"]:
            case "interrupt" | "broadcast_complete":
                priority = 1
            case "broadcast":
                priority = 2
            case "request" | "response":
                priority = 3

        await self.message_queue.put((priority, message))

        return

    def _process_message(self, user_token: str, message: ACPMessage) -> None:
        """
        The internal process for sending a message to the recipient agent(s)
        """
        msg_content = message["message"]

        if "recipients" in msg_content:
            if msg_content["recipients"] == ["all"]:  # type: ignore
                recipients = list(self.agents.keys())
                recipients.remove(message["message"]["sender"])
            else:
                recipients = msg_content["recipients"]  # type: ignore
        else:
            recipients = [msg_content["recipient"]]

        for recipient in recipients:
            self._send_message(user_token, recipient, message)

        return None

    def _send_message(self, user_token: str, recipient: str, message: ACPMessage) -> None:
        """
        Send a message to a recipient
        """
        logger.info(
            f'sending message: "{message["message"]["sender"]}" -> "{recipient}" with header "{message["message"]["header"]}"'
        )

        async def schedule(message: ACPMessage) -> None:
            try:
                if message["msg_type"] == "request":
                    req_id = message["message"]["request_id"]  # type: ignore
                    sender = message["message"]["sender"]
                else:
                    req_id = ""
                    sender = ""
                incoming_message = build_acp_xml(message)
                history = self.agent_histories[recipient]
                history.append(incoming_message)
                out, results = await self.agents[recipient](history, "required")
                history.append(results[0].completion)
                for tc in results:
                    if tc.tool_name in ACP_TOOL_NAMES:
                        result_message = tc.create_response_msg(
                            "Message sent. The response, if any, will be sent in the next user message."
                        )
                        history.append(result_message)

                for call in results:
                    match call.tool_name:
                        case "send_message":
                            if req_id and sender == call.tool_args["target"]:
                                await self.submit(
                                    convert_call_to_acp_message(call, recipient, req_id)
                                )
                            else:
                                await self.submit(
                                    convert_call_to_acp_message(call, recipient)
                                )
                        case "send_interrupt":
                            await self.submit(
                                convert_call_to_acp_message(call, recipient)
                            )
                        case "send_broadcast":
                            await self.submit(
                                convert_call_to_acp_message(call, recipient)
                            )
                        case "task_complete":
                            # Check if this completes a pending request
                            if req_id and req_id in self.pending_requests:
                                # Create a response message for the user
                                response_message = ACPMessage(
                                    id=str(uuid.uuid4()),
                                    timestamp=datetime.datetime.now(),
                                    message=ACPBroadcast(
                                        request_id=req_id,
                                        sender="supervisor",
                                        recipients=["all"],
                                        header="Task Complete",
                                        body=call.tool_args.get("finish_message", "Task completed successfully"),
                                    ),
                                    msg_type="broadcast_complete",
                                )
                                # Resolve the pending request
                                future = self.pending_requests.pop(req_id)
                                if not future.done():
                                    future.set_result(response_message)
                            
                            await self.submit(
                                convert_call_to_acp_message(call, recipient)
                            )
                        case _:
                            logger.info(f"executing action tool: {call.tool_name}")
                            result_message = await execute_action_tool(
                                call, self.actions
                            )
                            history.append(result_message)
                            await self.submit(
                                action_complete_broadcast(result_message, recipient)
                            )
                self.agent_histories[recipient] = history[1:]
            finally:
                self.message_queue.task_done()

        task = asyncio.create_task(schedule(message))
        self.active_tasks.add(task)

        task.add_done_callback(self.active_tasks.discard)

        return None

    def _system_shutdown_message(self, reason: str) -> ACPMessage:
        return ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(),
            message=ACPBroadcast(
                broadcast_id=str(uuid.uuid4()),
                sender="system",
                recipients=["user"],
                header="System Shutdown",
                body=reason,
            ),
            msg_type="response",
        )
