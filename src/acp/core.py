import asyncio
import datetime
import logging
from typing import Any, Optional
import uuid
from asyncio import PriorityQueue, Task

from .executor import execute_action_tool
from .message import ACPBroadcast, ACPMessage, build_acp_xml, ACPResponse, parse_agent_address
from .tools import (
    ACP_TOOL_NAMES,
    action_complete_broadcast,
    convert_call_to_acp_message,
)
from .factories.action import ActionFunction
from .factories.base import AgentFunction
from .interswarm_router import InterswarmRouter
from .swarm_registry import SwarmRegistry

logger = logging.getLogger("acp")


class ACP:
    def __init__(
        self,
        agents: dict[str, AgentFunction],
        actions: dict[str, ActionFunction],
        user_token: str = None,
        swarm_name: str = "default",
        swarm_registry: Optional[SwarmRegistry] = None,
        enable_interswarm: bool = False,
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
        
        # Interswarm messaging support
        self.swarm_name = swarm_name
        self.enable_interswarm = enable_interswarm
        self.swarm_registry = swarm_registry
        self.interswarm_router: Optional[InterswarmRouter] = None
        
        if enable_interswarm and swarm_registry:
            self.interswarm_router = InterswarmRouter(swarm_registry, swarm_name)
            # Register local message handler
            self.interswarm_router.register_message_handler("local_message_handler", self._handle_local_message)

    async def start_interswarm(self) -> None:
        """Start interswarm messaging capabilities."""
        if self.enable_interswarm and self.interswarm_router:
            await self.interswarm_router.start()
            logger.info(f"Started interswarm messaging for swarm: {self.swarm_name}")

    async def stop_interswarm(self) -> None:
        """Stop interswarm messaging capabilities."""
        if self.interswarm_router:
            await self.interswarm_router.stop()
            logger.info(f"Stopped interswarm messaging for swarm: {self.swarm_name}")

    async def _handle_local_message(self, message: ACPMessage) -> None:
        """Handle a message that should be processed locally."""
        await self.submit(message)

    async def handle_interswarm_response(self, response_message: ACPMessage) -> None:
        """Handle an incoming response from a remote swarm."""
        logger.info(f"Handling interswarm response: {response_message['id']}")
        
        # Submit the response to the local message queue for processing
        # This will allow the local supervisor agent to process the response
        # and generate a final response for the user
        await self.submit(response_message)
        
        # Don't immediately complete the pending request here
        # Let the local processing flow handle it naturally
        # The supervisor agent should process the response and generate
        # a final response that will complete the user's request

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
                logger.info(f"Pending requests: {self.pending_requests}")
                
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
                    # Check if this completes a pending request
                    msg_content = message["message"]
                    if "task_id" in msg_content and msg_content["task_id"] in self.pending_requests:
                        # Resolve the pending request
                        logger.info(f"Task {msg_content['task_id']} completed, resolving pending request")
                        future = self.pending_requests.pop(msg_content["task_id"])
                        if not future.done():
                            future.set_result(message)
                    else:
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
        This method is designed for handling individual task requests in a persistent ACP instance.
        """
        task_id = message["message"]["task_id"]
        user_id = self.user_token[:8] if self.user_token else 'unknown'
        
        logger.info(f"submitAndWait: Creating future for task {task_id} for user {user_id}")
        
        # Create a future to wait for the response
        future = asyncio.Future()
        self.pending_requests[task_id] = future
        
        try:
            # Submit the message
            logger.info(f"submitAndWait: Submitting message for task {task_id}")
            await self.submit(message)
            
            # Wait for the response with timeout
            logger.info(f"submitAndWait: Waiting for future for task {task_id}")
            response = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"submitAndWait: Got response for task {task_id}: {response['message']['body'][:50]}...")
            return response
            
        except asyncio.TimeoutError:
            # Remove the pending request
            self.pending_requests.pop(task_id, None)
            logger.error(f"submitAndWait: Timeout for task {task_id}")
            raise TimeoutError(f"Task {task_id} for user {user_id} timed out after {timeout} seconds")
        except Exception as e:
            # Remove the pending request
            self.pending_requests.pop(task_id, None)
            logger.error(f"submitAndWait: Exception for task {task_id}: {e}")
            raise e

    async def shutdown(self) -> None:
        """Request a graceful shutdown of the ACP system."""
        user_id = self.user_token[:8] if self.user_token else 'unknown'
        logger.info(f"requesting shutdown for user {user_id}...")
        
        # Stop interswarm messaging first
        if self.enable_interswarm:
            await self.stop_interswarm()
        
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
        # If interswarm messaging is enabled, try to route via interswarm router first
        if self.enable_interswarm and self.interswarm_router:
            # Check if any recipients are in interswarm format
            msg_content = message["message"]
            has_interswarm_recipients = False
            
            if "recipients" in msg_content:
                for recipient in msg_content["recipients"]:
                    _, recipient_swarm = parse_agent_address(recipient)
                    if recipient_swarm and recipient_swarm != self.swarm_name:
                        has_interswarm_recipients = True
                        break
            elif "recipient" in msg_content:
                _, recipient_swarm = parse_agent_address(msg_content["recipient"])
                if recipient_swarm and recipient_swarm != self.swarm_name:
                    has_interswarm_recipients = True
            
            if has_interswarm_recipients:
                # Route via interswarm router
                asyncio.create_task(self._route_interswarm_message(message))
                return
        
        # Fall back to local processing
        self._process_local_message(user_token, message)

    async def _route_interswarm_message(self, message: ACPMessage) -> None:
        """Route a message via interswarm router."""
        if self.interswarm_router:
            try:
                response = await self.interswarm_router.route_message(message)
                logger.info(f"Received response from remote swarm, processing locally: {response['id']}")
                self._process_local_message(self.user_token, response)
            except Exception as e:
                logger.error(f"Error in interswarm routing: {e}")
                # Fall back to local processing for failed interswarm messages
                self._process_local_message(self.user_token, message)
        else:
            logger.error("Interswarm router not available")
            # Fall back to local processing
            self._process_local_message(self.user_token, message)

    def _process_local_message(self, user_token: str, message: ACPMessage) -> None:
        """
        Process a message locally (original _process_message logic)
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
            # Parse recipient address to get local agent name
            recipient_agent, recipient_swarm = parse_agent_address(recipient)
            
            # Only process if this is a local agent or no swarm specified
            if not recipient_swarm or recipient_swarm == self.swarm_name:
                if recipient_agent in self.agents:
                    self._send_message(user_token, recipient_agent, message)
                else:
                    logger.warning(f"Unknown local agent: {recipient_agent}")
            else:
                logger.debug(f"Skipping remote agent {recipient} in local processing")

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
                task_id = message["message"]["task_id"]
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
                        case "send_request":
                            await self.submit(
                                convert_call_to_acp_message(call, recipient, task_id)
                            )
                        case "send_response":
                            await self.submit(
                                convert_call_to_acp_message(call, recipient, task_id)
                            )
                        case "send_interrupt":
                            await self.submit(
                                convert_call_to_acp_message(call, recipient, task_id)
                            )
                        case "send_broadcast":
                            await self.submit(
                                convert_call_to_acp_message(call, recipient, task_id)
                            )
                        case "task_complete":
                            # Check if this completes a pending request
                            if task_id and task_id in self.pending_requests:
                                logger.info(f"Task {task_id} completed, resolving pending request for user {self.user_token[:8] if self.user_token else 'unknown'}")
                                # Create a response message for the user
                                response_message = ACPMessage(
                                    id=str(uuid.uuid4()),
                                    timestamp=datetime.datetime.now().isoformat(),
                                    message=ACPBroadcast(
                                        task_id=task_id,
                                        broadcast_id=str(uuid.uuid4()),
                                        sender="supervisor",
                                        recipients=["all"],
                                        header="Task complete",
                                        body=call.tool_args.get("finish_message", "Task completed successfully"),
                                    ),
                                    msg_type="broadcast_complete",
                                )
                                # Resolve the pending request
                                future = self.pending_requests.pop(task_id)
                                if not future.done():
                                    logger.info(f"Resolving future for task {task_id}")
                                    future.set_result(response_message)
                                else:
                                    logger.warning(f"Future for task {task_id} was already done")
                                # Don't submit the duplicate message - we've already resolved the request
                            else:
                                logger.info(f"Task {task_id} completed but no pending request found, submitting message")
                                # Only submit the message if there's no pending request to resolve
                                await self.submit(
                                    convert_call_to_acp_message(call, recipient, task_id)
                                )
                        case _:
                            logger.info(f"executing action tool: {call.tool_name}")
                            result_message = await execute_action_tool(
                                call, self.actions
                            )
                            history.append(result_message)
                            await self.submit(
                                action_complete_broadcast(result_message, recipient, task_id)
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
            timestamp=datetime.datetime.now().isoformat(),
            message=ACPBroadcast(
                broadcast_id=str(uuid.uuid4()),
                sender="system",
                recipients=["user"],
                header="System Shutdown",
                body=reason,
            ),
            msg_type="response",
        )
