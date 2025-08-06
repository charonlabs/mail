# FastAPI server for ACP over HTTP

import datetime
import logging
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from toml import load as load_toml

from acp.core import ACP
from acp.message import ACPMessage, ACPRequest
from acp.logger import init_logger
from acp.swarms.builder import build_swarm_from_name
from acp.auth import login

# Initialize logger at module level so it runs regardless of how the server is started
init_logger()
logger = logging.getLogger("acp")

app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Charon server starting up...")
    yield
    # Shutdown
    logger.info("Charon server shutting down...")


@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    version = load_toml("pyproject.toml")["project"]["version"]
    return {"name": "acp", "status": "ok", "version": version}


@app.post("/chat")
async def chat(request: Request):
    """
    Handle chat requests from the client.
    Instantiates an ACP instance and passes the request to it as a new message, then returns the response.

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
        user_token = await login(api_key.split(" ")[1])
        logger.info(f"User authenticated with token: {user_token[:8]}...")
    else:
        logger.warning("Invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    # build swarm
    try:
        logger.info("Building swarm...")
        swarm = build_swarm_from_name("example")
        acp = swarm.instantiate(user_token)
        logger.info("Swarm built and instantiated successfully")
    except Exception as e:
        logger.error(f"Error building swarm: {e}")
        raise HTTPException(
            status_code=500, detail=f"error building swarm: {e.with_traceback(None)}"
        )

    # parse request
    try:
        data = await request.json()
        message = data.get("message", "")
        logger.info(f"Received message: {message[:50]}...")
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
        logger.info("Creating ACP message...")
        new_message = ACPMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(),
            message=ACPRequest(
                request_id=str(uuid.uuid4()),
                sender="user",
                recipient="supervisor",
                header="New Message",
                body=message,
            ),
            msg_type="request",
        )
        logger.info("Submitting message to ACP...")
        await acp.submit(new_message)
        logger.info("Running ACP...")
        response = await acp.run()
        logger.info("ACP completed successfully")
        return {"response": response["message"]["body"]}
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


if __name__ == "__main__":
    logger.info("Starting Charon server directly...")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)