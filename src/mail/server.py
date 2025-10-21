# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mail",
# ]
# ///

# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline, Will Hahn

import asyncio
import datetime
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from aiohttp import ClientSession
from fastapi import Depends, FastAPI, HTTPException, Request

import mail.net.server_utils as server_utils
import mail.utils as utils
from mail.config.server import ServerConfig
from mail.core.message import (
    MAIL_MESSAGE_TYPES,
    MAILAddress,
    MAILBroadcast,
    MAILInterswarmMessage,
    MAILMessage,
    MAILRequest,
    MAILResponse,
    create_address,
    format_agent_address,
    parse_agent_address,
)
from mail.net import types as types
from mail.utils.logger import init_logger

from .api import MAILSwarm, MAILSwarmTemplate

# Initialize logger at module level so it runs regardless of how the server is started
_server_config: ServerConfig = ServerConfig()
init_logger()
logger = logging.getLogger("mail.server")


def _log_prelude(app: FastAPI) -> str:
    """
    Get the log prelude for the server.
    """
    return f"[[green]{app.state.local_swarm_name}[/green]@{app.state.local_base_url}]"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle startup and shutdown events.
    """
    await _server_startup(app)

    yield

    await _server_shutdown(app)


async def _server_startup(app: FastAPI) -> None:
    """
    Server startup logic, run before the `yield` in the lifespan context manager.
    """
    logger.info("MAIL server starting up...")

    cfg = _server_config

    # set defaults
    # swarm stuff
    app.state.persistent_swarm = server_utils.get_default_persistent_swarm(cfg)
    app.state.admin_mail_instances = server_utils.init_mail_instances_dict()
    app.state.admin_mail_tasks = server_utils.init_mail_tasks_dict()
    app.state.user_mail_instances = server_utils.init_mail_instances_dict()
    app.state.user_mail_tasks = server_utils.init_mail_tasks_dict()
    app.state.swarm_mail_instances = server_utils.init_mail_instances_dict()
    app.state.swarm_mail_tasks = server_utils.init_mail_tasks_dict()
    app.state.task_bindings = server_utils.init_task_bindings_dict()

    # Interswarm messaging support
    app.state.swarm_registry = server_utils.get_default_swarm_registry(cfg)
    app.state.local_swarm_name = server_utils.get_default_swarm_name(cfg)
    app.state.local_base_url = server_utils.get_default_base_url(cfg)
    app.state.default_entrypoint_agent = server_utils.get_default_entrypoint_agent(
        app.state.persistent_swarm
    )

    # Shared HTTP session for any server-initiated interswarm calls
    app.state._http_session = ClientSession(
        headers={"User-Agent": f"MAIL-Server/v{utils.get_protocol_version()}/{app.state.local_swarm_name} (github.com/charonlabs/mail)"}
    )

    # more app state
    app.state.start_time = time.time()
    app.state.health = "healthy"
    app.state.last_health_update = app.state.start_time


def _register_task_binding(
    app: FastAPI,
    task_id: str,
    role: str,
    identifier: str,
    jwt: str,
    *,
    direct: bool = False,
) -> None:
    if not task_id:
        return
    binding = {
        "role": role,
        "id": identifier,
    }
    if jwt:
        binding["jwt"] = jwt
    if direct:
        binding["direct"] = True # type: ignore
    app.state.task_bindings[task_id] = binding


def _resolve_task_binding(app: FastAPI, task_id: str) -> dict[str, str] | None:
    return app.state.task_bindings.get(task_id)


def _find_instance_for_task(app: FastAPI, task_id: str) -> tuple[str, str, "MAILSwarm"] | None:
    def _scan(container: dict[str, "MAILSwarm"], role: str) -> tuple[str, str, "MAILSwarm"] | None:
        for identifier, instance in container.items():
            runtime = getattr(instance, "_runtime", None)
            if runtime is None:
                continue
            try:
                task = runtime.get_task_by_id(task_id)
            except Exception:
                task = None
            if task is not None:
                return (role, identifier, instance)
        return None

    for role, container in (
        ("admin", app.state.admin_mail_instances),
        ("user", app.state.user_mail_instances),
        ("swarm", app.state.swarm_mail_instances),
    ):
        found = _scan(container, role)
        if found is not None:
            return found
    return None


async def _server_shutdown(app: FastAPI) -> None:
    """
    Server shutdown logic, run after the `yield` in the lifespan context manager.
    """
    logger.info("MAIL server shutting down...")

    # Stop swarm registry and cleanup volatile endpoints
    if app.state.swarm_registry:
        await app.state.swarm_registry.stop_health_checks()
        # Clean up volatile endpoints and save persistent ones
        app.state.swarm_registry.cleanup_volatile_endpoints()

    # Clean up all admin MAIL instances
    for admin_id, mail_instance in app.state.admin_mail_instances.items():
        logger.info(
            f"{_log_prelude(app)} shutting down MAIL instance for admin '{admin_id}'"
        )
        await mail_instance.shutdown()

    for admin_id, mail_task in app.state.admin_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(
                f"{_log_prelude(app)} cancelling MAIL task for admin '{admin_id}'"
            )
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass

    # Clean up all user MAIL instances
    for user_id, mail_instance in app.state.user_mail_instances.items():
        logger.info(
            f"{_log_prelude(app)} shutting down MAIL instance for user '{user_id}'"
        )
        await mail_instance.shutdown()

    for user_id, mail_task in app.state.user_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(
                f"{_log_prelude(app)} cancelling MAIL task for user '{user_id}'"
            )
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass

    # Clean up all swarm MAIL instances
    for swarm_id, mail_instance in app.state.swarm_mail_instances.items():
        logger.info(
            f"{_log_prelude(app)} shutting down MAIL instance for swarm '{swarm_id}'"
        )
        await mail_instance.shutdown()

    for swarm_id, mail_task in app.state.swarm_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(
                f"{_log_prelude(app)} cancelling MAIL task for swarm '{swarm_id}'"
            )
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass

    # Close shared HTTP session if opened
    if app.state._http_session is not None:
        try:
            await app.state._http_session.close()
        except Exception:
            pass
        app.state._http_session = None


app = FastAPI(lifespan=lifespan)


async def get_or_create_mail_instance(
    role: Literal["admin", "swarm", "user"],
    id: str,
    jwt: str,
) -> MAILSwarm:
    """
    Get or create a MAIL instance for a specific role.
    """
    match role:
        case "admin":
            mail_instances = app.state.admin_mail_instances
            mail_tasks = app.state.admin_mail_tasks
        case "swarm":
            mail_instances = app.state.swarm_mail_instances
            mail_tasks = app.state.swarm_mail_tasks
        case "user":
            mail_instances = app.state.user_mail_instances
            mail_tasks = app.state.user_mail_tasks
        case _:
            raise ValueError(f"invalid role: {role}")

    existing_instance = mail_instances.get(id)
    if isinstance(existing_instance, MAILSwarm):
        return existing_instance
    if isinstance(existing_instance, asyncio.Task):
        logger.warning(
            f"{_log_prelude(app)} MAIL instance for {role} '{id}' was stored as a task; recreating runtime"
        )
        # Best effort: cancel the orphaned task if still running.
        try:
            if not existing_instance.done():
                existing_instance.cancel()
        except Exception:
            pass
        mail_instances.pop(id, None)
        mail_tasks.pop(id, None)

    if id not in mail_instances:
        try:
            logger.info(f"{_log_prelude(app)} creating MAIL instance for {role} '{id}'")

            ps = app.state.persistent_swarm
            mail_instance = ps.instantiate(
                instance_params={
                    "user_token": jwt,
                },
                user_id=id,
                user_role=role,
                base_url=app.state.local_base_url,
                registry_file=app.state.swarm_registry.persistence_file,
            )
            mail_instances[id] = mail_instance

            # Start interswarm messaging
            await mail_instance.start_interswarm()

            # Start the MAIL instance in continuous mode for this role
            logger.info(
                f"{_log_prelude(app)} starting MAIL continuous mode for {role} '{id}'"
            )
            mail_task = asyncio.create_task(
                mail_instance.run_continuous(
                    max_steps=app.state.persistent_swarm.task_message_limit
                )
            )
            mail_tasks[id] = mail_task

            logger.info(
                f"{_log_prelude(app)} MAIL instance created and started for {role} '{id}'"
            )

        except Exception as e:
            logger.error(
                f"{_log_prelude(app)} error creating MAIL instance for {role} '{id}' with error: '{e}'"
            )
            raise e

    instance = mail_instances.get(id)
    if isinstance(instance, MAILSwarm):
        return instance

    raise RuntimeError(
        f"MAIL instance for {role} '{id}' is unavailable after creation attempt"
    )


@app.get("/")
async def root():
    """
    Return basic info about the server.
    """
    return types.GetRootResponse(
        name="mail",
        version=utils.get_protocol_version(),
        swarm=app.state.local_swarm_name,
        status="running",
        uptime=time.time() - app.state.start_time,
    )


@app.get("/health")
async def health():
    """
    Health check endpoint for interswarm communication.
    """
    return types.GetHealthResponse(
        status=app.state.health,
        swarm_name=app.state.local_swarm_name,
        timestamp=datetime.datetime.fromtimestamp(
            app.state.last_health_update, datetime.UTC
        ).isoformat(),
    )


@app.post("/health", dependencies=[Depends(utils.caller_is_admin)])
async def health_post(request: Request):
    """
    Update the server's health status.
    """
    data = await request.json()
    status = data.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status is required")

    app.state.health = status
    app.state.last_health_update = time.time()

    return types.GetHealthResponse(
        status=app.state.health,
        swarm_name=app.state.local_swarm_name,
        timestamp=datetime.datetime.fromtimestamp(
            app.state.last_health_update, datetime.UTC
        ).isoformat(),
    )


@app.get("/whoami", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def whoami(request: Request):
    """
    Get the username and role of the caller.
    """
    try:
        caller_info = await utils.extract_token_info(request)
        return types.GetWhoamiResponse(id=caller_info["id"], role=caller_info["role"])
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"{_log_prelude(app)} error getting whoami: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error getting whoami: {e.with_traceback(None)}"
        )


@app.get("/status", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def status(request: Request):
    """
    Get the status of the persistent swarm and user-specific MAIL instances.
    """
    caller_info = await utils.extract_token_info(request)
    caller_id = caller_info["id"]
    caller_role = caller_info["role"]
    match caller_role:
        case "admin":
            mail_instances = app.state.admin_mail_instances
            mail_tasks = app.state.admin_mail_tasks
        case "user":
            mail_instances = app.state.user_mail_instances
            mail_tasks = app.state.user_mail_tasks
        case _:
            raise ValueError(f"invalid role: {caller_role}")

    user_mail_status = caller_id in mail_instances
    user_task_running = caller_id in mail_tasks and not mail_tasks[caller_id].done()

    return types.GetStatusResponse(
        swarm={
            "name": app.state.persistent_swarm.name
            if app.state.persistent_swarm
            else None,
            "status": "ready",
        },
        active_users=len(app.state.user_mail_instances),
        user_mail_ready=user_mail_status,
        user_task_running=user_task_running,
    )


@app.post("/message", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def message(request: Request):
    """
    Handle message requests from the client.
    Uses a user-specific MAIL instance to process the request and returns the response.

    Args:
        body: The string containing the message.
        subject: The subject of the message.
        msg_type: The type of the message.
        entrypoint: The entrypoint to use for the message.
        show_events: Whether to return the events for the task.
        stream: Whether to stream the response.
        task_id: The task ID to use for the message.
        resume_from: The type of resume to use for the message.
        **kwargs: Additional keyword arguments to pass to the runtime.run_task method.

    Returns:
        A dictionary containing the response message.
    """
    caller_info = await utils.extract_token_info(request)
    caller_id = caller_info["id"]
    caller_role = caller_info["role"]

    # Extract bearer token from header for runtime instance params
    auth_header = request.headers.get("Authorization", "")
    jwt = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else ""

    # Get or create user-specific MAIL instance (for readiness tracking/interswarm)
    try:
        await get_or_create_mail_instance(caller_role, caller_id, jwt)
    except Exception as e:
        logger.error(
            f"{_log_prelude(app)} error getting {caller_role} MAIL instance: '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error getting {caller_role} MAIL instance: {e.with_traceback(None)}",
        )

    # parse request
    try:
        data = await request.json()
        body = data.get("body") or ""
        subject = data.get("subject") or "New Message"
        msg_type = data.get("msg_type") or "request"
        entrypoint = data.get("entrypoint")
        task_id = data.get("task_id")
        resume_from = data.get("resume_from")
        kwargs = data.get("kwargs") or {}
        # Choose recipient: provided entrypoint or default from config
        if isinstance(entrypoint, str) and entrypoint.strip():
            recipient_agent = entrypoint.strip()
        else:
            recipient_agent = app.state.default_entrypoint_agent
        show_events = data.get("show_events", False)
        stream = data.get("stream", False)

        assert isinstance(msg_type, str)
        if msg_type not in MAIL_MESSAGE_TYPES:
            raise HTTPException(
                status_code=400, detail=f"invalid message type: {msg_type}"
            )

        logger.info(
            f"{_log_prelude(app)} received message from {caller_role} '{caller_id}': '{subject}'"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"{_log_prelude(app)} error parsing request: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not body:
        logger.warning(f"{_log_prelude(app)} no message body provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # MAIL process
    try:
        assert app.state.persistent_swarm is not None

        api_swarm = await get_or_create_mail_instance(caller_role, caller_id, jwt)

        if not isinstance(task_id, str) or not task_id:
            task_id = str(uuid.uuid4())
        _register_task_binding(app, task_id, caller_role, caller_id, jwt)

        # If client provided an explicit entrypoint, pass it through; otherwise use default
        chosen_entrypoint = recipient_agent

        if stream:
            logger.info(
                f"{_log_prelude(app)} submitting streamed message via MAIL API for {caller_role} '{caller_id}'"
            )
            return await api_swarm.post_message_stream(
                subject=subject,
                body=body,
                msg_type=msg_type,  # type: ignore
                entrypoint=chosen_entrypoint,
                task_id=task_id,
                resume_from=resume_from,
                **kwargs,
            )
        else:
            logger.info(
                f"{_log_prelude(app)} submitting message via MAIL API for {caller_role} '{caller_id}' and waiting"
            )
            result = await api_swarm.post_message(
                subject=subject,
                body=body,
                msg_type=msg_type,  # type: ignore
                entrypoint=chosen_entrypoint,
                show_events=show_events,
                task_id=task_id,
                resume_from=resume_from,
                **kwargs,
            )
            # Support both (response, events) and response-only returns
            if isinstance(result, tuple) and len(result) == 2:
                response, events = result
            else:
                response, events = result, []  # type: ignore[misc]

            return types.PostMessageResponse(
                response=response["message"]["body"],
                events=events if show_events else None,
            )

    except Exception as e:
        logger.error(
            f"{_log_prelude(app)} error processing message for {caller_role} '{caller_id}' with error: '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.get("/swarms")
async def list_swarms():
    """
    List all known swarms for service discovery.
    """
    if not app.state.swarm_registry:
        raise HTTPException(status_code=503, detail="swarm registry not available")

    endpoints = app.state.swarm_registry.get_all_endpoints()

    swarms = [types.SwarmEndpoint(**endpoint) for endpoint in endpoints.values()]

    return types.GetSwarmsResponse(
        swarms=swarms,
    )


@app.post("/swarms", dependencies=[Depends(utils.caller_is_admin)])
async def register_swarm(request: Request):
    """
    Register a new swarm in the registry.
    Only admins can register new swarms.
    If "volatile" is False, the swarm will be persistent and will not be removed from the registry when the server shuts down.
    """
    if not app.state.swarm_registry:
        raise HTTPException(status_code=503, detail="swarm registry not available")

    try:
        # parse request
        data = await request.json()
        swarm_name = data.get("name")
        base_url = data.get("base_url")
        auth_token = data.get("auth_token")
        volatile = data.get("volatile", True)
        metadata = data.get("metadata")

        if not swarm_name or not base_url:
            raise HTTPException(
                status_code=400, detail="name and base_url are required"
            )

        app.state.swarm_registry.register_swarm(
            swarm_name, base_url, auth_token, metadata, volatile
        )
        return types.PostSwarmsResponse(
            status="registered",
            swarm_name=swarm_name,
        )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"{_log_prelude(app)} error registering swarm: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error registering swarm: '{str(e)}'"
        )


@app.get("/swarms/dump", dependencies=[Depends(utils.caller_is_admin)])
async def dump_swarm(request: Request):
    """
    Dump the persistent swarm to the console.
    """
    assert app.state.persistent_swarm is not None

    # log da swarm
    logger.info(
        f"{_log_prelude(app)} current persistent swarm: name='{app.state.persistent_swarm.name}', agents={[agent.name for agent in app.state.persistent_swarm.agents]}"
    )

    # all done!
    return types.GetSwarmsDumpResponse(
        status="dumped",
        swarm_name=app.state.persistent_swarm.name,
    )


@app.post("/interswarm/message", dependencies=[Depends(utils.caller_is_agent)])
async def receive_interswarm_message(request: Request):
    """
    Receive an interswarm message from another swarm.
    """
    caller_info = await utils.extract_token_info(request)
    caller_id = caller_info["id"]
    auth_header = request.headers.get("Authorization", "")
    jwt = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else ""

    # Get or create swarm-specific MAIL instance
    try:
        swarm_mail = await get_or_create_mail_instance("swarm", caller_id, jwt)
    except Exception as e:
        logger.error(
            f"{_log_prelude(app)} error getting swarm MAIL instance for '{caller_id}': '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error getting swarm MAIL instance: {e.with_traceback(None)}",
        )

    # parse request
    try:
        data = await request.json()
        interswarm_message = MAILInterswarmMessage(**data)  # type: ignore
        message = interswarm_message["payload"]
        source_swarm = interswarm_message["source_swarm"]
        source_agent = message.get("sender", {})
        target_agent = message.get("recipient", {})

        logger.info(
            f"{_log_prelude(app)} received message from {source_agent} to {target_agent}: {message.get('subject', 'unknown')}"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"{_log_prelude(app)} error parsing request: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning(f"{_log_prelude(app)} no message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # MAIL process
    try:
        metadata = data.get("metadata") or {}

        logger.info(
            f"{_log_prelude(app)} creating MAIL message for swarm '{source_swarm}'"
        )
        new_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=message,
            msg_type=data.get("msg_type", "request"),
        )
        logger.info(
            f"{_log_prelude(app)} submitting message '{new_message['id']}' to agent MAIL and waiting for response"
        )
        if metadata.get("stream"):
            ignore_pings = bool(metadata.get("ignore_stream_pings"))
            ping_interval = None if ignore_pings else 15000
            return await swarm_mail.submit_message_stream(
                new_message,
                ping_interval=ping_interval,
            )

        submit_result = await swarm_mail.submit_message(new_message)
        # Support both (response, events) and response-only returns
        if isinstance(submit_result, tuple) and len(submit_result) == 2:
            task_response = submit_result[0]
        else:
            task_response = submit_result  # type: ignore[assignment]

        # Create response message
        response_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILResponse(
                task_id=task_response["message"]["task_id"],
                request_id=task_response["message"].get(
                    "request_id", task_response["message"]["task_id"]
                ),  # type: ignore
                sender=task_response["message"]["sender"],
                recipient=source_agent,
                subject=task_response["message"]["subject"],
                body=task_response["message"]["body"],
                sender_swarm=app.state.local_swarm_name,
                recipient_swarm=source_swarm,
                routing_info={},
            ),
            msg_type="response",
        )

        # Return the MAILMessage directly to match expected shape.
        logger.info(
            f"{_log_prelude(app)} MAIL completed successfully for swarm '{source_swarm}'"
        )
        return response_message

    except Exception as e:
        logger.error(
            f"{_log_prelude(app)} error processing message for swarm '{source_swarm}' with error: '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.post("/interswarm/response", dependencies=[Depends(utils.caller_is_agent)])
async def receive_interswarm_response(request: Request):
    """
    Receive an interswarm response from another swarm.
    """
    # parse request
    try:
        data = await request.json()
        response_message = MAILMessage(**data)  # type: ignore
        logger.info(
            f"{_log_prelude(app)} received interswarm response from '{response_message['message']['sender']}': '{response_message['message']['subject']}'"
        )
    except Exception as e:
        logger.error(f"{_log_prelude(app)} error parsing interswarm response: '{e}'")
        raise HTTPException(
            status_code=400,
            detail=f"error parsing interswarm response: {e.with_traceback(None)}",
        )

    task_id = response_message["message"]["task_id"]
    binding = _resolve_task_binding(app, task_id)
    mail_instance = None

    if binding is not None:
        target_role = binding.get("role")
        target_id = binding.get("id")
        target_jwt = binding.get("jwt", "")
        if binding.get("direct"):
            located = _find_instance_for_task(app, task_id)
            if located is not None:
                _, _, mail_instance = located
        elif target_role in {"admin", "user", "swarm"} and isinstance(target_id, str):
            try:
                mail_instance = await get_or_create_mail_instance(
                    target_role, target_id, target_jwt  # type: ignore[arg-type]
                )
            except Exception as e:
                logger.error(
                    f"{_log_prelude(app)} error getting MAIL instance for task '{task_id}' owner '{target_role}:{target_id}': '{e}'"
                )
                mail_instance = None

    if mail_instance is None:
        located = _find_instance_for_task(app, task_id)
        if located is not None:
            role, identifier, instance = located
            mail_instance = instance
            if task_id not in app.state.task_bindings:
                _register_task_binding(app, task_id, role, identifier, "", direct=True)

    if mail_instance is None:
        # Fallback to swarm-instance routing (legacy behavior)
        try:
            swarm_jwt = utils.extract_token(request)
            mail_instance = await get_or_create_mail_instance(
                "swarm", response_message["message"]["sender_swarm"], swarm_jwt
            )
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            logger.error(
                f"{_log_prelude(app)} error getting swarm MAIL instance for '{response_message['message']['sender_swarm']}': '{e}'"
            )
            raise HTTPException(
                status_code=500,
                detail=f"error getting swarm MAIL instance: {e.with_traceback(None)}",
            )

    if mail_instance is None:
        return types.PostInterswarmResponseResponse(
            status="no_mail_instance",
            task_id=task_id,
        )

    # The incoming response already targets the original requester (often supervisor)
    # with a proper MAILAddress. Route it into the runtime as-is.
    await mail_instance.handle_interswarm_response(response_message)
    logger.info(
        f"{_log_prelude(app)} response submitted to MAIL instance for task '{task_id}'"
    )

    return types.PostInterswarmResponseResponse(
        status="response_processed",
        task_id=task_id,
    )


@app.post("/interswarm/send", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def send_interswarm_message(request: Request):
    """
    Send an interswarm message to another swarm.
    Intended for users and admins.

    Args:
        targets: The targets to send the message to.
        body: The message to send.
        subject: The subject of the message.
        msg_type: The type of the message.
        task_id: The task ID of the message.
        routing_info: The routing information for the message.
        stream: Whether to stream the message.
        ignore_stream_pings: Whether to ignore stream pings.
        user_token: The user token to use for the message.

    Returns:
        The response from the message.
    """
    try:
        caller_info = await utils.extract_token_info(request)
        caller_id = caller_info["id"]
        caller_role = caller_info["role"]
        assert caller_role in ["admin", "user"]

        # parse request
        data = await request.json()
        targets = data.get("targets")
        message_content = data.get("body")
        subject = data.get("subject", "Interswarm Message")
        msg_type = data.get("msg_type", "request")
        raw_task_id = data.get("task_id")
        task_id = raw_task_id if isinstance(raw_task_id, str) and raw_task_id else str(uuid.uuid4())
        routing_info = data.get("routing_info") or {}
        stream_requested = bool(data.get("stream"))
        ignore_pings = bool(data.get("ignore_stream_pings"))
        if stream_requested:
            routing_info["stream"] = True
            if ignore_pings:
                routing_info["ignore_stream_pings"] = True
        elif ignore_pings:
            routing_info["ignore_stream_pings"] = True

        user_token = data.get("user_token")
        if not user_token:
            raise HTTPException(status_code=401, detail="user token is required")

        if message_content is not None and not isinstance(message_content, str):
            message_content = str(message_content)

        if subject is not None and not isinstance(subject, str):
            subject = str(subject)

        if not targets or not message_content:
            raise HTTPException(
                status_code=400,
                detail="'targets' and 'body' are required",
            )

        mail_instance = await get_or_create_mail_instance(
            caller_role, caller_id, user_token
        )
        _register_task_binding(app, task_id, caller_role, caller_id, user_token or "")

        sender_address = create_address(caller_id, caller_role)

        def _build_request(target: str) -> MAILMessage:
            recipient_agent, recipient_swarm = parse_agent_address(target)
            recipient_address = format_agent_address(recipient_agent, recipient_swarm)
            return MAILMessage(
                id=str(uuid.uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILRequest(
                    task_id=task_id,
                    request_id=str(uuid.uuid4()),
                    sender=sender_address,
                    recipient=recipient_address,
                    subject=subject,
                    body=message_content,
                    sender_swarm=app.state.local_swarm_name,
                    recipient_swarm=recipient_swarm or app.state.local_swarm_name,
                    routing_info=routing_info,
                ),
                msg_type="request",
            )

        def _build_broadcast() -> MAILMessage:
            recipients: list[MAILAddress] = []
            recipient_swarms: set[str] = set()
            for target in targets:
                agent, swarm = parse_agent_address(target)
                recipients.append(format_agent_address(agent, swarm))
                if swarm:
                    recipient_swarms.add(swarm)
            return MAILMessage(
                id=str(uuid.uuid4()),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                message=MAILBroadcast(
                    task_id=task_id,
                    broadcast_id=str(uuid.uuid4()),
                    sender=sender_address,
                    recipients=recipients,
                    subject=subject,
                    body=message_content,
                    sender_swarm=app.state.local_swarm_name,
                    recipient_swarms=list(recipient_swarms)
                    or [app.state.local_swarm_name],
                    routing_info=routing_info,
                ),
                msg_type="broadcast",
            )

        match msg_type:
            case "request":
                if len(targets) != 1:
                    raise HTTPException(
                        status_code=400,
                        detail="'request' messages require exactly one target",
                    )
                mail_message = _build_request(targets[0])
            case "broadcast":
                mail_message = _build_broadcast()
            case _:
                raise HTTPException(
                    status_code=400,
                    detail=f"msg_type '{msg_type}' is not supported for interswarm send",
                )

        # Route the message
        if mail_instance.enable_interswarm:
            response = await mail_instance.route_interswarm_message(mail_message)
            return types.PostInterswarmSendResponse(
                response=response,
                events=None,
            )
        else:
            raise HTTPException(
                status_code=503, detail="interswarm router not available"
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"{_log_prelude(app)} error sending interswarm message: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error sending interswarm message: '{str(e)}'"
        )


@app.post("/swarms/load", dependencies=[Depends(utils.caller_is_admin)])
async def load_swarm_from_json(request: Request):
    """
    Load a swarm from a JSON string.
    """
    # get the json string from the request
    data = await request.json()
    swarm_json = data.get("json")

    try:
        # try to load the swarm from string and set the persistent swarm
        app.state.persistent_swarm = MAILSwarmTemplate.from_swarm_json(swarm_json)
        return types.PostSwarmsLoadResponse(
            status="success",
            swarm_name=app.state.persistent_swarm.name,
        )
    except Exception as e:
        # shit hit the fan
        logger.error(f"{_log_prelude(app)} error loading swarm from JSON: {e}")
        raise HTTPException(
            status_code=500, detail=f"error loading swarm from JSON: {e}"
        )


def run_server(
    cfg: ServerConfig,
):
    logger.info("starting MAIL server directly...")

    # Ensure the server lifespan uses the runtime config supplied via CLI or caller.
    global _server_config
    _server_config = cfg

    os.environ["SWARM_NAME"] = cfg.swarm.name
    os.environ["SWARM_REGISTRY_FILE"] = cfg.swarm.registry_file
    os.environ["SWARM_SOURCE"] = cfg.swarm.source
    os.environ.setdefault("BASE_URL", server_utils.compute_external_base_url(cfg))

    uvicorn.run("mail.server:app", host=cfg.host, port=cfg.port, reload=cfg.reload)


if __name__ == "__main__":
    run_server(
        cfg=ServerConfig(),
    )
