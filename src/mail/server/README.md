# mail-server

`mail-server` provides a FastAPI-based `MAILServer` wrapper for serving a local
MAIL swarm over HTTP.

## Basic usage

```python
from mail_protocol.core.swarm import MAILSwarm
from mail_server import MAILServer

server = MAILServer(
    swarm=MAILSwarm(
        name="example",
        agents=["supervisor"],
        entrypoints=["supervisor"],
        keywords=["demo"],
        description="Example MAIL server",
        metadata={},
    ),
    registry_path="./registry.json",
)


@server.on_startup
async def startup(mail_server: MAILServer) -> None:
    ...


@server.on_shutdown
async def shutdown(mail_server: MAILServer) -> None:
    ...


@server.on_message
async def handle_message(message):
    return message, {}


@server.on_interswarm_message
async def handle_interswarm_message(message):
    return message, {}


server.run()
```

## Registry persistence

If `registry_path` is set, `MAILServer` will:

- load persisted registry entries on startup
- keep registry writes in memory for the current process
- persist all non-volatile entries on shutdown
