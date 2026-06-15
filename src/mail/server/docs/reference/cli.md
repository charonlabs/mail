# `mail-server` CLI

This document serves as a reference for the `mail-server` command-line interface (CLI) in Python.

## Usage

```bash
mail-server [option]...
```

## Options

- `-H`/`--host`: Set the IP address to bind to.
  - **Default**: `127.0.0.1`
  - **Example**: `mail-server --host 0.0.0.0`
- `-p`/`--port`: The port for the MAIL server to listen on.
  - **Default**: `8865`
  - **Example**: `mail-server --port 8000`
- `-b`/`--backend`: The MAIL server backend to use.
  - **Default**: `memory`
  - **Choices**: `memory`
  - **Example**: `mail-server --backend memory`
- `--memory-save-interval`: Seconds between memory backend filesystem checkpoints.
  - **Default**: `60`
  - **Environment**: `MAIL_MEMORY_SAVE_INTERVAL_SECONDS`
  - **Disable**: Set to `0` to rely only on startup/shutdown persistence.
  - **Example**: `mail-server --memory-save-interval 30`
