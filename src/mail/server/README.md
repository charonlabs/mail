# mail-server

`mail-server` provides a FastAPI-based `MAILServer` wrapper for serving a local
MAIL swarm over HTTP.

## Basic usage

```python
from mail_protocol.core.swarm import MAILSwarm
from mail_server import JWTSettings, MAILServer, StaticAPIKeyAuthBackend, TokenInfo

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
    auth_backend=StaticAPIKeyAuthBackend(
        {
            "admin-key": TokenInfo(role="admin", id="admin-1"),
            "user-key": TokenInfo(role="user", id="user-1"),
            "swarm-key": TokenInfo(role="swarm", id="remote-swarm"),
        }
    ),
    auth_settings=JWTSettings(
        secret="change-me",
        algorithm="HS256",
        lifetime_minutes=60,
    ),
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


@server.on_interswarm
async def handle_interswarm_message(message):
    return message, {}


server.run()
```

`POST /login` accepts `{"api_key": "..."}` and returns a JWT access token. That
token is then used as `Authorization: Bearer <token>` for protected endpoints
such as `POST /message`, `POST /registry`, and `DELETE /registry/{swarm_name}`.

For production, replace `StaticAPIKeyAuthBackend` with your own backend object
that implements `authenticate_api_key(api_key) -> TokenInfo | None`. That
lookup can come from a database, external auth service, or any custom user
management system.

## Registry persistence

If `registry_path` is set, `MAILServer` will:

- load persisted registry entries on startup
- keep registry writes in memory for the current process
- persist all non-volatile entries on shutdown
