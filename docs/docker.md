# Docker Deployment

This guide explains how to build and run the MAIL reference server in a Docker container. Use it when you want an immutable runtime or need to deploy MAIL to container platforms.

## Prerequisites
- Docker 24+
- Python 3.12-compatible base image (the example uses `python:3.12-slim`)
- Access to the MAIL repository source tree when building the image

## Example Dockerfile
Place the following `Dockerfile` at the repository root or in a build-specific folder. It mirrors the workflow used throughout the docs (`uv sync` for dependency resolution):

```Dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

# Install system dependencies used during the build
RUN apt-get update \ \
    && apt-get install -y --no-install-recommends curl build-essential \ \
    && rm -rf /var/lib/apt/lists/*

# uv handles dependency resolution and execution
RUN pip install --no-cache-dir uv

# Copy dep metadata first to leverage Docker layer caching
COPY pyproject.toml uv.lock mail.toml ./
RUN uv sync --frozen --no-dev

# Copy the remaining source files required by the server
COPY src ./src
COPY spec ./spec
COPY docs ./docs

# Default configuration; override via `mail.toml`/`MAIL_CONFIG_PATH` or CLI flags
ENV PORT=8000 \
    AUTH_ENDPOINT=http://auth.local/login \
    TOKEN_INFO_ENDPOINT=http://auth.local/token-info \
    LITELLM_PROXY_API_BASE=http://litellm.local

EXPOSE 8000
CMD ["uv", "run", "mail", "server", "--host", "0.0.0.0", "--port", "8000"]
```

### Multi-stage tip
If you want a smaller runtime image, split the `Dockerfile` into build and final stages. Copy `.venv` from the build stage to the runtime stage and strip out build-essential packages there.

## Build the image
```bash
docker build -t mail-server .
```
The build context must contain the repository so that the `COPY` commands pick up the source and configuration files.

## Run the container
The server requires the same environment variables as the native quickstart (`AUTH_ENDPOINT`, `TOKEN_INFO_ENDPOINT`, and `LITELLM_PROXY_API_BASE` only if your swarm uses `use_proxy=true`). Pass them via `--env` flags or an env file. To change swarm name/source/registry, mount a custom `mail.toml` and set `MAIL_CONFIG_PATH` or pass `mail server --swarm-name/--swarm-source/--swarm-registry` in the container command.

```bash
# Option 1: export locally then forward with --env
export AUTH_ENDPOINT=http://127.0.0.1:8999/login
export TOKEN_INFO_ENDPOINT=http://127.0.0.1:8999/token-info
export LITELLM_PROXY_API_BASE=http://127.0.0.1:8080

docker run --rm \
  -p 8000:8000 \
  -e AUTH_ENDPOINT \
  -e TOKEN_INFO_ENDPOINT \
  -e LITELLM_PROXY_API_BASE \
  mail-server
```

```bash
# Option 2: use an env file
cat <<'ENVVARS' > .env.mail
AUTH_ENDPOINT=http://127.0.0.1:8999/login
TOKEN_INFO_ENDPOINT=http://127.0.0.1:8999/token-info
LITELLM_PROXY_API_BASE=http://127.0.0.1:8080
ENVVARS

docker run --rm -p 8000:8000 --env-file .env.mail mail-server
```

`mail server` seeds `SWARM_SOURCE` and `SWARM_REGISTRY_FILE` from `mail.toml`; set them explicitly if you mount alternative swarm definitions or persistence paths into the container.

### Persisting registries and logs
Mount host directories if you want the container to keep swarm registry data or logs between runs:

```bash
docker run --rm \
  -p 8000:8000 \
  --env-file .env.mail \
  -v $(pwd)/registries:/app/registries \
  -v $(pwd)/logs:/app/logs \
  mail-server
```

## Health checks
Use the same endpoints as the quickstart for readiness and status:

```bash
curl http://localhost:8000/health
curl -H "Authorization: Bearer user:demo" http://localhost:8000/status
```

Update the URLs to the forwarded host/port if you publish the container through ngrok or another ingress.

## Troubleshooting
- Ensure Docker is forwarding the port (`-p 8000:8000`) and no other service is bound to that port on the host.
- Confirm the authentication service is reachable from inside the container. If you expose a host service via `localhost`, use the Docker host gateway (`host.docker.internal` on macOS/Windows or `--add-host` on Linux).
- Rebuild the image after dependency changes; Docker layer caching only applies when `pyproject.toml`/`uv.lock` remain unchanged.
```
