# MAIL HTTP API

This document serves as a reference for the MAIL (Mult-Agent Interface Layer) HTTP API.

## Endpoint Summaries

### Default

- `GET /`: Obtain basic server information and metadata.
- `GET /health`: Get a status message for the MAIL server's current health.

### Authentication

- `POST /auth/token`: Log in with a valid MAIL address and password to obtain a temporary access token.
- `GET /auth/whoami`: Obtain information on the logged-in MAIL server user-agent.
- `POST /auth/password/reset`: Reset the logged-in user-agent's password.

### Swarms

- `GET /swarms/`: Obtain the list of swarms hosted on this MAIL server.
- `GET /swarms/{swarm_name}`: Get a specific swarm by name hosted on this MAIL server.
- `GET /swarms/{swarm_name}/health`: Get a status message for ths given swarm's current health.

### Inbox

- `GET /inbox/`: Get a list of messages in the logged-in user-agent's inbox.
- `GET /inbox/{message_id}`: Get a specific message by ID in the logged-in user-agent's inbox.
- `DELETE /inbox/{message_id}`: Move a specific message by ID in the logged-in user-agent's inbox to their trash.

### Outbox

- `GET /outbox/`: Get a list of messages in the logged-in user-agent's outbox.
- `GET /outbox/{message_id}`: Get a specific message by ID in the logged-in user-agent's outbox.

### Drafts

- `GET /drafts/`: Get a list of message drafts in the logged-in user-agent's draft box.
- `POST /drafts/`: Create a new message draft to be stored in the logged-in user-agent's draft box.
- `GET /drafts/{draft_id}`: Get a specific message draft by ID from the logged-in user-agent's draft box.
- `DELETE /drafts/{draft_id}`: Delete a specific message draft by ID from the logged-in user-agent's draft box.
- `POST /drafts/{draft_id}/send`: Send a message from a draft by ID in the logged-in user-agent's draft box.

### Trash

- `GET /trash/`: Get a list of messages in the logged-in user-agent's trash box.
- `GET /trash/{message_id}`: Get a specific message by ID in the logged-in user-agent's trash box.
- `DELETE /trash/{message_id}`: Delete a specific message by ID in the logged-in user-agent's trash box.
- `POST /trash/clear`: Remove all existing messages in the logged-in user-agent's trash box.

### Daemon

- `POST /daemon/message-buffer/clear`: Obtain the IDs of all messages in need for delivery and clear the server's buffer.
- `POST /daemon/deliver/local`: Upload a list of message IDs to deliver to user-agents on this server.
- `POST /daemon/deliver/remote`: Upload a list of messages from remote MAIL servers to deliver to user-agents on this server.

### Admin

- `GET /admin/agents`: Get a list of agents by local address (agent@swarm) from the MAIL server.
- `POST /admin/agents`: Creat a new MAIL agent for this server.
- `GET /admin/agents/{agent_address}`: Get a specific registered agent by local address (agent@swarm).
- `DELETE /admin/agents/{agent_address}`: Delete an existing registered agent by local address (agent@swarm).
- `GET /admin/daemons`: Get a list of daemons by worker name from the MAIL server.
- `POST /admin/daemons`: Create a new MAIL daemon for this server.
- `GET /admin/daemons/{worker_name}`: Get a specific registered daemon by worker name.
- `DELETE /admin/daemons/{worker_name}`: Delete an existing daemon by worker name from the server.
- `GET /admin/users`: Get a list of users by user ID from the MAIL server.
- `POST /admin/users`: Create a new MAIL user for this server.
- `GET /admin/users/{user_id}`: Get a specific registered user by user ID.
- `DELETE /admin/users/{user_id}`: Delete an existing user by ID from the server.
- `POST /admin/swarms`: Create a new MAIL swarm on the server.
- `DELETE /admin/swawms/{swarm_name}`: Delete an existing MAIL swarm from the server.
- `GET /admin/webhooks`: Get the IDs of all existing webhooks on this MAIL server.
- `POST /admin/webhooks`: Create a new webhook on the MAIL server.
- `GET /admin/webhooks/{webhook_id}`: Get an existing server webhook by ID.
- `DELETE /admin/webhooks/{webhook_id}`: Delete an existing server webhook by ID.
- `PATCH /admin/webhooks/{webhook_id}`: Update an existing server webhook by ID.
