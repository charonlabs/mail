FROM python:3.12-slim AS base
WORKDIR /app

# system deps (curl used for health checks; build-essential for uv install if needed)
RUN apt-get update && apt-get install -y curl build-essential && rm -rf /var/lib/apt/lists/*

# install uv (preferred workflow)
RUN pip install --no-cache-dir uv

# copy dependency metadata and resolve deps
COPY pyproject.toml uv.lock mail.toml ./
RUN uv sync --frozen --no-dev

# copy application code
COPY src ./src

# set required env vars at runtime, or rely on docker run -e ...
ENV PORT=8000 \
    AUTH_ENDPOINT=http://auth.local/login \
    TOKEN_INFO_ENDPOINT=http://auth.local/token-info \
    LITELLM_PROXY_API_BASE=http://litellm.local \
    SWARM_NAME=example-no-proxy \
    BASE_URL=http://localhost:8000

EXPOSE 8000
CMD ["uv", "run", "mail", "server", "--host", "0.0.0.0", "--port", "8000"]
