# FastAPI server for ACP over HTTP

import datetime
import logging
import uuid
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from toml import load as load_toml

from .core import ACP
from .message import ACPMessage, ACPRequest, ACPInterswarmMessage, ACPResponse
from .logger import init_logger
from .swarms.builder import build_swarm_from_name
from .auth import login
from .swarm_registry import SwarmRegistry

# Initialize logger at module level so it runs regardless of how the server is started
init_logger()
logger = logging.getLogger("acp")

# Global variables 
persistent_swarm = None
user_acp_instances: Dict[str, ACP] = {}
user_acp_tasks: Dict[str, asyncio.Task] = {}
agent_acp_instances: Dict[str, ACP] = {}
agent_acp_tasks: Dict[str, asyncio.Task] = {}

# Interswarm messaging support
swarm_registry: Optional[SwarmRegistry] = None
local_swarm_name: str = "default"
local_base_url: str = "http://localhost:8000"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("ACP server starting up...")
    
    # Initialize swarm registry for interswarm messaging
    global swarm_registry, local_swarm_name, local_base_url
    
    # Get configuration from environment
    local_swarm_name = os.getenv("SWARM_NAME", "default")
    local_base_url = os.getenv("BASE_URL", "http://localhost:8000")
    
    swarm_registry = SwarmRegistry(local_swarm_name, local_base_url)
    
    # Start health checks
    await swarm_registry.start_health_checks()
    
    # Create persistent swarm at startup
    global persistent_swarm
    try:
        logger.info("Building persistent swarm...")
        persistent_swarm = build_swarm_from_name(local_swarm_name)
        logger.info("Persistent swarm built successfully")
    except Exception as e:
        logger.error(f"Error building persistent swarm: {e}")
        raise e
    
    yield
    
    # Shutdown
    logger.info("ACP server shutting down...")
    
    # Stop swarm registry
    if swarm_registry:
        await swarm_registry.stop_health_checks()
    
    # Clean up all user ACP instances
    global user_acp_instances, user_acp_tasks
    for user_token, acp_instance in user_acp_instances.items():
        logger.info(f"Shutting down ACP instance for user: {user_token[:8]}...")
        await acp_instance.shutdown()
    
    for user_token, acp_task in user_acp_tasks.items():
        if acp_task and not acp_task.done():
            logger.info(f"Cancelling ACP task for user: {user_token[:8]}...")
            acp_task.cancel()
            try:
                await acp_task
            except asyncio.CancelledError:
                pass

    # Clean up all agent ACP instances
    global agent_acp_instances, agent_acp_tasks
    for agent_id, acp_instance in agent_acp_instances.items():
        logger.info(f"Shutting down ACP instance for agent: {agent_id}...")
        await acp_instance.shutdown()
    
    for agent_id, acp_task in agent_acp_tasks.items():
        if acp_task and not acp_task.done():
            logger.info(f"Cancelling ACP task for agent: {agent_id}...")
            acp_task.cancel()
            try:
                await acp_task
            except asyncio.CancelledError:
                pass

app = FastAPI(lifespan=lifespan)

async def get_or_create_user_acp(jwt: str) -> ACP:
    """
    Get or create an ACP instance for a specific user.
    Each user gets their own isolated ACP instance.
    """
    global persistent_swarm, user_acp_instances, user_acp_tasks, swarm_registry
    
    # TODO: implement user_id from jwt
    user_id = jwt

    if user_id not in user_acp_instances:
        try:
            logger.info(f"Creating ACP instance for user: {user_id[:8]}...")
            
            # Create a new ACP instance for this user with interswarm support
            acp_instance = persistent_swarm.instantiate(
                user_token=jwt, 
                swarm_name=local_swarm_name,
                swarm_registry=swarm_registry,
                enable_interswarm=True
            )
            user_acp_instances[user_id] = acp_instance
            
            # Start interswarm messaging
            await acp_instance.start_interswarm()
            
            # Start the ACP instance in continuous mode for this user
            logger.info(f"Starting ACP continuous mode for user: {user_id[:8]}...")
            acp_task = asyncio.create_task(acp_instance.run_continuous())
            user_acp_tasks[user_id] = acp_task
            
            logger.info(f"ACP instance created and started for user: {user_id[:8]}")
            
        except Exception as e:
            logger.error(f"Error creating ACP instance for user {user_id[:8]}: {e}")
            raise e
    
    return user_acp_instances[user_id]

async def get_or_create_agent_acp(jwt: str) -> ACP:
    """
    Get or create an ACP instance for a specific agent.
    Each agent gets their own isolated ACP instance.
    """
    global persistent_swarm, agent_acp_instances, agent_acp_tasks, swarm_registry
    
    # TODO: implement agent_id from jwt
    agent_id = jwt

    if agent_id not in agent_acp_instances:
        try:
            logger.info(f"Creating ACP instance for agent: {agent_id[:8]}...")
            
            # Create a new ACP instance for this user with interswarm support
            acp_instance = persistent_swarm.instantiate(
                user_token=jwt, 
                swarm_name=local_swarm_name,
                swarm_registry=swarm_registry,
                enable_interswarm=True
            )
            agent_acp_instances[agent_id] = acp_instance
            
            # Start interswarm messaging
            await acp_instance.start_interswarm()
            
            # Start the ACP instance in continuous mode for this user
            logger.info(f"Starting ACP continuous mode for agent: {agent_id[:8]}...")
            acp_task = asyncio.create_task(acp_instance.run_continuous())
            agent_acp_tasks[agent_id] = acp_task
            
            logger.info(f"ACP instance created and started for agent: {agent_id[:8]}")
            
        except Exception as e:
            logger.error(f"Error creating ACP instance for agent {agent_id[:8]}: {e}")
            raise e
    
    return agent_acp_instances[agent_id]


@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    version = load_toml("pyproject.toml")["project"]["version"]
    return {"name": "acp", "status": "ok", "version": version}


@app.get("/status")
async def status(request: Request):
    """Get the status of the persistent swarm and user-specific ACP instances."""
    global persistent_swarm, user_acp_instances, user_acp_tasks
    
    # Get user token from request
    api_key = request.headers.get("Authorization")
    if api_key and api_key.startswith("Bearer "):
        user_id = api_key.split(" ")[1]
        user_acp_status = user_id in user_acp_instances
        user_task_running = user_id in user_acp_tasks and not user_acp_tasks[user_id].done() if user_id in user_acp_tasks else False
    else:
        user_acp_status = False
        user_task_running = False
    
    return {
        "swarm": {"name": persistent_swarm.name if persistent_swarm else None, "status": "ready"},
        "active_users": len(user_acp_instances),
        "user_acp_ready": user_acp_status,
        "user_task_running": user_task_running
    }


@app.post("/chat")
async def chat(request: Request):
    """
    Handle chat requests from the client.
    Uses a user-specific ACP instance to process the request and returns the response.

    Args:
        request: The request object containing the chat message.

    Returns:
        A dictionary containing the response message.
    """
    logger.info("Chat endpoint accessed")

    # auth process
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("No API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info(f"User authenticated with token: {jwt[:8]}...")
    else:
        logger.warning("Invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    # Get or create user-specific ACP instance
    try:
        user_acp = await get_or_create_user_acp(jwt)
    except Exception as e:
        logger.error(f"Error getting user ACP instance: {e}")
        raise HTTPException(
            status_code=500, detail=f"error getting user ACP instance: {e.with_traceback(None)}"
        )

    # parse request
    try:
        data = await request.json()
        message = data.get("message", "")
        logger.info(f"Received message from user {jwt[:8]}: {message[:50]}...")
    except Exception as e:
        logger.error(f"Error parsing request: {e}")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("No message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # ACP process
    try:
        logger.info(f"Creating ACP message for user {jwt[:8]}...")
        new_message = ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(),
            message=ACPRequest(
                task_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                sender="user",
                recipient="supervisor",
                header="New Message",
                body=message,
            ),
            msg_type="request",
        )
        logger.info(f"Submitting message to user ACP and waiting for response...")
        response = await user_acp.submit_and_wait(new_message)
        logger.info(f"ACP completed successfully for user {jwt[:8]}")
        return {"response": response["message"]["body"]}
    except Exception as e:
        logger.error(f"Error processing message for user {jwt[:8]}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.get("/health")
async def health():
    """Health check endpoint for interswarm communication."""
    return {
        "status": "healthy",
        "swarm_name": local_swarm_name,
        "timestamp": datetime.datetime.now().isoformat()
    }


@app.get("/swarms")
async def list_swarms():
    """List all known swarms for service discovery."""
    global swarm_registry
    if not swarm_registry:
        raise HTTPException(status_code=503, detail="Swarm registry not available")
    
    endpoints = swarm_registry.get_all_endpoints()
    swarms = []
    
    for name, endpoint in endpoints.items():
        swarms.append({
            "name": endpoint.swarm_name,
            "base_url": endpoint.base_url,
            "is_active": endpoint.is_active,
            "last_seen": endpoint.last_seen.isoformat() if endpoint.last_seen else None,
            "metadata": endpoint.metadata
        })
    
    return {"swarms": swarms}


@app.post("/swarms/register")
async def register_swarm(request: Request):
    """Register a new swarm in the registry."""
    global swarm_registry
    if not swarm_registry:
        raise HTTPException(status_code=503, detail="Swarm registry not available")
    
    try:
        data = await request.json()
        swarm_name = data.get("name")
        base_url = data.get("base_url")
        auth_token = data.get("auth_token")
        metadata = data.get("metadata")
        
        if not swarm_name or not base_url:
            raise HTTPException(status_code=400, detail="name and base_url are required")
        
        swarm_registry.register_swarm(swarm_name, base_url, auth_token, metadata)
        return {"status": "registered", "swarm_name": swarm_name}
        
    except Exception as e:
        logger.error(f"Error registering swarm: {e}")
        raise HTTPException(status_code=500, detail=f"Error registering swarm: {str(e)}")


@app.post("/interswarm/message")
async def receive_interswarm_message(request: Request):
    """Receive an interswarm message from another swarm."""
    logger.info("Interswarm message endpoint accessed")

    # auth process
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("No API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info(f"Agent authenticated with token: {jwt[:8]}...")
    else:
        logger.warning("Invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    # Get or create agent-specific ACP instance
    try:
        agent_acp = await get_or_create_agent_acp(jwt)
    except Exception as e:
        logger.error(f"Error getting agent ACP instance: {e}")
        raise HTTPException(
            status_code=500, detail=f"error getting agent ACP instance: {e.with_traceback(None)}"
        )

    # parse request
    try:
        data = await request.json()
        message = data.get("payload", {})
        source_agent = f"{message.get("sender", "unknown")}@{data.get("source_swarm", "unknown")}"
        target_agent = f"{message.get("recipient", "unknown")}"
        message["sender"] = source_agent
        logger.info(f"Received message from agent {source_agent} to agent {target_agent}: {message.get("header", "unknown")}...")
    except Exception as e:
        logger.error(f"Error parsing request: {e}")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("No message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # ACP process
    try:
        logger.info(f"Creating ACP message for agent {source_agent}...")
        new_message = ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now().isoformat(),
            message=message,
            msg_type=data.get("msg_type", "request"),
        )
        logger.info(f"Submitting message to agent ACP and waiting for response...")
        task_response = await agent_acp.submit_and_wait(new_message)
        response = ACPMessage(
            id=task_response["id"],
            timestamp=task_response["timestamp"],
            message=ACPResponse(
                task_id=task_response["message"]["task_id"],
                request_id=task_response["message"]["task_id"],
                sender=task_response["message"]["sender"],
                recipient=source_agent,
                header=task_response["message"]["header"],
                body=task_response["message"]["body"],
            ),
            msg_type=task_response["msg_type"],
        )
        logger.info(f"ACP completed successfully for agent {source_agent}")
        return response
    except Exception as e:
        logger.error(f"Error processing message for agent {source_agent}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.post("/interswarm/send")
async def send_interswarm_message(request: Request):
    """Send an interswarm message to another swarm."""
    global swarm_registry, user_acp_instances
    
    try:
        data = await request.json()
        target_agent = data.get("target_agent")
        message_content = data.get("message")
        user_token = data.get("user_token")
        
        if not target_agent or not message_content:
            raise HTTPException(status_code=400, detail="target_agent and message are required")
        
        if not user_token or user_token not in user_acp_instances:
            raise HTTPException(status_code=400, detail="Valid user_token is required")
        
        acp_instance = user_acp_instances[user_token]
        
        # Create ACP message
        acp_message = ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(),
            message=ACPRequest(
                task_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                sender="user",
                recipient=f"{target_agent}",
                header="Interswarm Message",
                body=message_content,
                sender_swarm=local_swarm_name,
                recipient_swarm=target_agent.split("@")[1]
            ),
            msg_type="request",
        )
        
        # Route the message
        if acp_instance.interswarm_router:
            response = await acp_instance.interswarm_router.route_message(acp_message)
            return response
        else:
            raise HTTPException(status_code=503, detail="Interswarm router not available")
            
    except Exception as e:
        logger.error(f"Error sending interswarm message: {e}")
        raise HTTPException(status_code=500, detail=f"Error sending interswarm message: {str(e)}")


if __name__ == "__main__":
    logger.info("Starting ACP server directly...")
    port = int(os.getenv("BASE_URL", "http://localhost:8000").split(":")[-1])
    uvicorn.run("acp.server:app", host="0.0.0.0", port=port, reload=True)