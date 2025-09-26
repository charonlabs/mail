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
import uuid
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from toml import load as load_toml

import mail.utils as utils
from mail.core.message import (
    MAILInterswarmMessage,
    MAILMessage,
    MAILRequest,
    MAILResponse,
    create_agent_address,
    create_user_address,
)
from mail.net import types as types
from mail.net.registry import SwarmRegistry
from mail.utils.logger import init_logger

from .api import MAILSwarm, MAILSwarmTemplate

# Initialize logger at module level so it runs regardless of how the server is started
init_logger()
logger = logging.getLogger("mail.server")

# Global variables
persistent_swarm: MAILSwarmTemplate | None = None
user_mail_instances: dict[str, MAILSwarm] = {}
user_mail_tasks: dict[str, asyncio.Task] = {}
swarm_mail_instances: dict[str, MAILSwarm] = {}
swarm_mail_tasks: dict[str, asyncio.Task] = {}

# Interswarm messaging support
swarm_registry: SwarmRegistry | None = None
local_swarm_name: str = "example-no-proxy"
local_base_url: str = "http://localhost:8000"
default_entrypoint_agent: str = "supervisor"

# Shared HTTP session for any server-initiated interswarm calls
_http_session: aiohttp.ClientSession | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle startup and shutdown events.
    """
    # Startup
    logger.info("MAIL server starting up...")

    # Initialize swarm registry for interswarm messaging
    global swarm_registry, local_swarm_name, local_base_url

    # Get configuration from environment
    local_swarm_name = os.getenv("SWARM_NAME", "example-no-proxy")
    local_base_url = os.getenv("BASE_URL", "http://localhost:8000")
    persistence_file = os.getenv("SWARM_REGISTRY_FILE", "registries/example.json")

    swarm_registry = SwarmRegistry(local_swarm_name, local_base_url, persistence_file)

    # Start health checks
    await swarm_registry.start_health_checks()

    # Create persistent swarm at startup
    global persistent_swarm
    try:
        logger.info("building persistent swarm...")
        persistent_swarm = MAILSwarmTemplate.from_swarm_json_file(
            local_swarm_name, "swarms.json"
        )
        logger.info("persistent swarm built successfully")
        # Load default entrypoint from config
        global default_entrypoint_agent
        default_entrypoint_agent = persistent_swarm.entrypoint
        logger.info(
            f"default entrypoint for swarm '{local_swarm_name}': '{default_entrypoint_agent}'"
        )
    except Exception as e:
        logger.error(f"error building persistent swarm: '{e}'")
        raise e

    yield

    # Shutdown
    logger.info("MAIL server shutting down...")

    # Stop swarm registry and cleanup volatile endpoints
    if swarm_registry:
        await swarm_registry.stop_health_checks()
        # Clean up volatile endpoints and save persistent ones
        swarm_registry.cleanup_volatile_endpoints()

    # Clean up all user MAIL instances
    global user_mail_instances, user_mail_tasks
    for user_id, mail_instance in user_mail_instances.items():
        logger.info(f"shutting down MAIL instance for user: '{user_id}'...")
        await mail_instance.shutdown()

    for user_id, mail_task in user_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(f"cancelling MAIL task for user: '{user_id}'...")
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass

    # Clean up all swarm MAIL instances
    global swarm_mail_instances, swarm_mail_tasks
    for swarm_id, mail_instance in swarm_mail_instances.items():
        logger.info(f"shutting down MAIL instance for swarm: '{swarm_id}'...")
        await mail_instance.shutdown()

    for swarm_id, mail_task in swarm_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(f"cancelling MAIL task for swarm: '{swarm_id}'...")
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass

    # Close shared HTTP session if opened
    global _http_session
    if _http_session is not None:
        try:
            await _http_session.close()
        except Exception:
            pass
        _http_session = None


app = FastAPI(lifespan=lifespan)


async def get_or_create_user_mail(user_id: str, jwt: str) -> MAILSwarm:
    """
    Get or create a MAIL instance for a specific user.
    Each user gets their own isolated MAIL instance.
    """
    global persistent_swarm, user_mail_instances, user_mail_tasks, swarm_registry

    assert persistent_swarm is not None
    assert swarm_registry is not None

    if user_id not in user_mail_instances:
        try:
            logger.info(f"creating MAIL instance for user: '{user_id}'...")

            # Create a new MAIL instance for this user with interswarm support
            mail_instance = persistent_swarm.instantiate(
                instance_params={
                    "user_token": jwt,
                },
                user_id=user_id,
                base_url=local_base_url,
                registry_file=swarm_registry.persistence_file,
            )
            user_mail_instances[user_id] = mail_instance

            # Start interswarm messaging
            await mail_instance.start_interswarm()

            # Start the MAIL instance in continuous mode for this user
            logger.info(f"starting MAIL continuous mode for user: '{user_id}'...")
            mail_task = asyncio.create_task(mail_instance.run_continuous())
            user_mail_tasks[user_id] = mail_task

            logger.info(f"MAIL instance created and started for user: '{user_id}'")

        except Exception as e:
            logger.error(
                f"error creating MAIL instance for user '{user_id}' with error: '{e}'"
            )
            raise e

    return user_mail_instances[user_id]


async def get_or_create_swarm_mail(swarm_id: str, jwt: str) -> MAILSwarm:
    """
    Get or create a MAIL instance for a specific swarm.
    Each swarm gets their own isolated MAIL instance.
    """
    global persistent_swarm, swarm_mail_instances, swarm_mail_tasks, swarm_registry

    assert persistent_swarm is not None
    assert swarm_registry is not None

    if swarm_id not in swarm_mail_instances:
        try:
            logger.info(f"creating MAIL instance for swarm: '{swarm_id}'...")

            # Create a new MAIL instance for this user with interswarm support
            mail_instance = persistent_swarm.instantiate(
                instance_params={
                    "user_token": jwt,
                },
                user_id=swarm_id,
                base_url=local_base_url,
                registry_file=swarm_registry.persistence_file,
            )
            swarm_mail_instances[swarm_id] = mail_instance

            # Start interswarm messaging
            await mail_instance.start_interswarm()

            # Start the MAIL instance in continuous mode for this user
            logger.info(f"starting MAIL continuous mode for swarm: '{swarm_id}'...")
            mail_task = asyncio.create_task(mail_instance.run_continuous())
            swarm_mail_tasks[swarm_id] = mail_task

            logger.info(f"MAIL instance created and started for swarm: '{swarm_id}'")

        except Exception as e:
            logger.error(
                f"error creating MAIL instance for swarm '{swarm_id}' with error: '{e}'"
            )
            raise e

    return swarm_mail_instances[swarm_id]


@app.get("/")
async def root():
    """
    Return basic info about the server.
    """
    logger.info("endpoint accessed: 'GET /'")

    try:
        version = load_toml("pyproject.toml")["project"]["version"]
    except Exception as e:
        logger.error(f"error loading version: '{e}'")
        raise HTTPException(status_code=500, detail=f"error loading version: {e}")

    return types.GetRootResponse(name="mail", status="ok", version=version)


@app.get("/status", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def status(request: Request):
    """
    Get the status of the persistent swarm and user-specific MAIL instances.
    """
    logger.info("endpoint accessed: 'GET /status'")

    global persistent_swarm, user_mail_instances, user_mail_tasks

    caller_info = await utils.extract_token_info(request)
    caller_id = utils.generate_user_id(caller_info)
    user_mail_status = caller_id in user_mail_instances
    user_task_running = (
        caller_id in user_mail_tasks and not user_mail_tasks[caller_id].done()
        if caller_id in user_mail_tasks
        else False
    )

    return types.GetStatusResponse(
        swarm={
            "name": persistent_swarm.name if persistent_swarm else None,
            "status": "ready",
        },
        active_users=len(user_mail_instances),
        user_mail_ready=user_mail_status,
        user_task_running=user_task_running,
    )


@app.post("/message", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def message(request: Request):
    """
    Handle message requests from the client.
    Uses a user-specific MAIL instance to process the request and returns the response.

    Args:
        message: The string containing the message.
        entrypoint: The entrypoint to use for the message.
        show_events: Whether to return the events for the task.
        stream: Whether to stream the response.

    Returns:
        A dictionary containing the response message.
    """
    logger.info("endpoint accessed: 'POST /message'")

    caller_info = await utils.extract_token_info(request)
    caller_id = utils.generate_user_id(caller_info)

    # Extract bearer token from header for runtime instance params
    auth_header = request.headers.get("Authorization", "")
    jwt = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else ""

    # Get or create user-specific MAIL instance (for readiness tracking/interswarm)
    try:
        await get_or_create_user_mail(caller_id, jwt)
    except Exception as e:
        logger.error(f"error getting user MAIL instance: '{e}'")
        raise HTTPException(
            status_code=500,
            detail=f"error getting user MAIL instance: {e.with_traceback(None)}",
        )

    # parse request
    try:
        data = await request.json()
        message = data.get("message", "")
        entrypoint = data.get("entrypoint")
        # Choose recipient: provided entrypoint or default from config
        if isinstance(entrypoint, str) and entrypoint.strip():
            recipient_agent = entrypoint.strip()
        else:
            recipient_agent = default_entrypoint_agent
        show_events = data.get("show_events", False)
        stream = data.get("stream", False)
        logger.info(
            f"received message from user or admin '{caller_id}': '{message[:50]}...'"
        )
    except Exception as e:
        logger.error(f"error parsing request: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("no message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # MAIL process
    try:
        assert persistent_swarm is not None

        api_swarm = await get_or_create_user_mail(caller_id, jwt)

        # If client provided an explicit entrypoint, pass it through; otherwise use default
        chosen_entrypoint = recipient_agent

        if stream:
            logger.info(
                f"submitting streamed message via MAIL API for user or admin '{caller_id}'..."
            )
            return await api_swarm.post_message_stream(
                subject="New Message", body=message, entrypoint=chosen_entrypoint
            )
        else:
            logger.info(
                f"submitting message via MAIL API for user or admin '{caller_id}' and waiting..."
            )
            result = await api_swarm.post_message(
                subject="New Message",
                body=message,
                entrypoint=chosen_entrypoint,
                show_events=show_events,
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
            f"error processing message for user or admin '{caller_id}' with error: '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.get("/health")
async def health():
    """
    Health check endpoint for interswarm communication.
    """
    logger.info("endpoint accessed: 'GET /health'")

    return types.GetHealthResponse(
        status="healthy",
        swarm_name=local_swarm_name,
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
    )


@app.get("/swarms")
async def list_swarms():
    """
    List all known swarms for service discovery.
    """
    logger.info("endpoint accessed: 'GET /swarms'")

    global swarm_registry
    if not swarm_registry:
        raise HTTPException(status_code=503, detail="swarm registry not available")

    endpoints = swarm_registry.get_all_endpoints()

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
    logger.info("endpoint accessed: 'POST /swarms'")

    global swarm_registry
    if not swarm_registry:
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

        swarm_registry.register_swarm(
            swarm_name, base_url, auth_token, metadata, volatile
        )
        return types.PostSwarmsResponse(
            status="registered",
            swarm_name=swarm_name,
        )

    except Exception as e:
        logger.error(f"error registering swarm: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error registering swarm: '{str(e)}'"
        )


@app.get("/swarms/dump", dependencies=[Depends(utils.caller_is_admin)])
async def dump_swarm(request: Request):
    """
    Dump the persistent swarm to the console.
    """
    logger.info("endpoint accessed: 'GET /swarms/dump'")

    global persistent_swarm

    assert persistent_swarm is not None

    # log da swarm
    logger.info(
        f"current persistent swarm: name='{persistent_swarm.name}', agents={[agent.name for agent in persistent_swarm.agents]}"
    )

    # all done!
    return types.GetSwarmsDumpResponse(
        status="dumped",
        swarm_name=persistent_swarm.name,
    )


@app.post("/interswarm/message", dependencies=[Depends(utils.caller_is_agent)])
async def receive_interswarm_message(request: Request):
    """
    Receive an interswarm message from another swarm.
    """
    logger.info("endpoint accessed: 'POST /interswarm/message'")

    caller_info = await utils.extract_token_info(request)
    caller_id = utils.generate_agent_id(caller_info)
    auth_header = request.headers.get("Authorization", "")
    jwt = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else ""

    # Get or create swarm-specific MAIL instance
    try:
        swarm_mail = await get_or_create_swarm_mail(caller_id, jwt)
    except Exception as e:
        logger.error(f"error getting swarm MAIL instance: '{e}'")
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
            f"received message from {source_agent} to {target_agent}: {message.get('subject', 'unknown')}..."
        )
    except Exception as e:
        logger.error(f"error parsing request: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("no message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # MAIL process
    try:
        logger.info(f"creating MAIL message for swarm '{source_swarm}'...")
        new_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=message,
            msg_type=data.get("msg_type", "request"),
        )
        logger.info(
            f"submitting message '{new_message['id']}' to agent MAIL and waiting for response..."
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
                sender_swarm=local_swarm_name,
                recipient_swarm=source_swarm,
                routing_info={},
            ),
            msg_type="response",
        )

        # Return the MAILMessage directly to match expected shape.
        logger.info(f"MAIL completed successfully for swarm '{source_swarm}'")
        return response_message

    except Exception as e:
        logger.error(
            f"error processing message for swarm '{source_swarm}' with error: '{e}'"
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
    logger.info("endpoint accessed: 'POST /interswarm/response'")

    # parse request
    try:
        data = await request.json()
        response_message = MAILMessage(**data)  # type: ignore
        logger.info(
            f"received response from '{response_message['message']['sender']}': '{response_message['message']['subject']}'..."
        )
    except Exception as e:
        logger.error(f"error parsing response: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing response: {e.with_traceback(None)}"
        )

    # Find the appropriate MAIL instance to handle this response
    # We need to match it based on the task_id or request_id
    global user_mail_instances, swarm_mail_instances

    # Try to find the MAIL instance that sent the original request
    task_id = response_message["message"]["task_id"]

    # Look through all MAIL instances to find one with pending requests
    mail_instance = None
    for _user_id, user_mail in user_mail_instances.items():
        if task_id in user_mail.get_pending_requests():
            mail_instance = user_mail
            break

    if not mail_instance:
        for _swarm_id, swarm_mail in swarm_mail_instances.items():
            if task_id in swarm_mail.get_pending_requests():
                mail_instance = swarm_mail
                break

    if mail_instance:
        # The incoming response already targets the original requester (often supervisor)
        # with a proper MAILAddress. Route it into the runtime as-is.
        await mail_instance.handle_interswarm_response(response_message)
        logger.info(f"response submitted to MAIL instance for task '{task_id}'")
        return types.PostInterswarmResponseResponse(
            status="response_processed",
            task_id=task_id,
        )
    else:
        logger.warning(f"no MAIL instance found for task '{task_id}'")
        return types.PostInterswarmResponseResponse(
            status="no_mail_instance",
            task_id=task_id,
        )


@app.post("/interswarm/send", dependencies=[Depends(utils.caller_is_admin_or_user)])
async def send_interswarm_message(request: Request):
    """
    Send an interswarm message to another swarm.
    Intended for users and admins.
    """
    logger.info("endpoint accessed: 'POST /interswarm/send'")

    global swarm_registry, user_mail_instances

    try:
        caller_info = await utils.extract_token_info(request)
        user_id = utils.generate_user_id(caller_info)

        # parse request
        data = await request.json()
        target_agent = data.get("target_agent")
        message_content = data.get("message")
        user_token = data.get("user_token")

        if not target_agent or not message_content:
            raise HTTPException(
                status_code=400, detail="target_agent and message are required"
            )

        if not user_token or user_token not in user_mail_instances:
            raise HTTPException(status_code=400, detail="Valid user_token is required")

        mail_instance = user_mail_instances[user_token]

        # Create MAIL message
        mail_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            message=MAILRequest(
                task_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                sender=create_user_address(f"{user_id}@{local_swarm_name}"),
                recipient=create_agent_address(f"{target_agent}"),
                subject="Interswarm Message",
                body=message_content,
                sender_swarm=local_swarm_name,
                recipient_swarm=target_agent.split("@")[1],
                routing_info={},
            ),
            msg_type="request",
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
                status_code=503, detail="Interswarm router not available"
            )

    except Exception as e:
        logger.error(f"error sending interswarm message: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error sending interswarm message: '{str(e)}'"
        )


@app.post("/swarms/load", dependencies=[Depends(utils.caller_is_admin)])
async def load_swarm_from_json(request: Request):
    """
    Load a swarm from a JSON string.
    """
    # got to let them know (shouting emoji)
    logger.info("endpoint accessed: 'POST /swarms/load'")

    global persistent_swarm

    # get the json string from the request
    data = await request.json()
    swarm_json = data.get("json")

    try:
        # try to load the swarm from string and set the persistent swarm
        persistent_swarm = MAILSwarmTemplate.from_swarm_json(swarm_json)
        return types.PostSwarmsLoadResponse(
            status="success",
            swarm_name=persistent_swarm.name,
        )
    except Exception as e:
        # shit hit the fan
        logger.error(f"error loading swarm from JSON: {e}")
        raise HTTPException(
            status_code=500, detail=f"error loading swarm from JSON: {e}"
        )


def run_server(
    host: str,
    port: int,
    reload: bool,
):
    logger.info("starting MAIL server directly...")
    uvicorn.run("mail.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run_server(
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
