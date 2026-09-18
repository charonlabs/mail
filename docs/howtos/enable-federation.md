# Enable and Operate MAIL Federation

## Goal

Configure two independently deployed MAIL servers to exchange signed messages,
rotate their Ed25519 keys safely, inspect failures, and disable federation
without deleting delivery state.

## Starting point

Assume two public DNS names, `mail-a.example.com` and `mail-b.example.com`, each
point to a TLS reverse proxy in front of a MAIL server. Use the SQLite backend
for crash-safe delivery attempts. Each deployment needs its own JWT secret,
federation key, database, user-agent credentials, and environment.

Do not use the private-host or insecure-transport test overrides in production.
If peers use a private CA, set `MAIL_FEDERATION_CA_FILE` to its PEM certificate
bundle on each origin; public deployments normally use the system trust store.

## 1. Initialize each server

Run this once for each host, changing the deployment and host values:

```bash
uv run backend-init \
  --type sqlite \
  --deployment server-a \
  --host mail-a.example.com

uv run backend-init \
  --type sqlite \
  --deployment server-b \
  --host mail-b.example.com
```

The default cast includes `daemon:dummy@<host>` with `deliver:local` and
`daemon:bounces@<host>` with `bounce:emit`. Securely capture the generated
passwords from each deployment's `.secrets/` directory.

## 2. Generate signing keys

Create a private directory owned by the server process and generate one key per
server:

```bash
install -d -m 0700 /etc/mail/server-a /etc/mail/server-b
uv run mail-federation-key generate /etc/mail/server-a/federation.pem \
  --key-id server-a-2026-09
uv run mail-federation-key generate /etc/mail/server-b/federation.pem \
  --key-id server-b-2026-09
```

The command refuses to overwrite a path and prints only the public value. Use
`inspect` at any time to reproduce that value:

```bash
uv run mail-federation-key inspect /etc/mail/server-a/federation.pem \
  --key-id server-a-2026-09 --json
```

## 3. Configure each process

Give server A its own values and allow server B; mirror them for B:

```env
MAIL_HOST=mail-a.example.com
MAIL_JWT_SECRET_KEY={unique-random-secret}
MAIL_JWT_ALGORITHM=HS256
MAIL_JWT_EXPIRE_MINUTES=30
MAIL_REFRESH_TOKEN_EXPIRE_DAYS=30

MAIL_FEDERATION_ENABLED=true
MAIL_FEDERATION_PUBLIC_HOST=mail-a.example.com
MAIL_FEDERATION_DELIVERY_URL=https://mail-a.example.com/daemon/deliver/remote/v1
MAIL_FEDERATION_KEY_ID=server-a-2026-09
MAIL_FEDERATION_PRIVATE_KEY_FILE=/etc/mail/server-a/federation.pem
MAIL_FEDERATION_POLICY=allowlist
MAIL_FEDERATION_ALLOWLIST=mail-b.example.com
```

For server B, use `MAIL_HOST`/`MAIL_FEDERATION_PUBLIC_HOST=mail-b.example.com`,
the B delivery URL and private key, key ID `server-b-2026-09`, and
`MAIL_FEDERATION_ALLOWLIST=mail-a.example.com`. Never share the JWT secret or
private key between deployments.

Start the application on a private bind address; the bind host is independent
of the advertised identity:

```bash
uv run mail-server --backend sqlite \
  --sqlite-path ~/.mail-swarms/deployments/server-a/mail.db \
  --host 127.0.0.1 --port 8865
```

Also run each deployment's local `mail-daemon` using its generated `dummy`
credentials (use B's URL/address/password on B):

```bash
MAIL_SERVER=http://127.0.0.1:8865 \
MAIL_ADDRESS=daemon:dummy@mail-a.example.com \
MAIL_PASSWORD={server-a-daemon-password} \
uv run mail-daemon
```

The server-owned federation worker handles inter-server attempts; the daemon
performs the final local inbox delivery and delivers local DSNs.

## 4. Preserve signed request inputs at the proxy

Expose both public paths over HTTPS:

- `GET /.well-known/mail-federation`
- `POST /daemon/deliver/remote/v1`

The application must observe the same target URI and authority the peer signed.
Preserve the public `Host` authority and original HTTPS scheme, and do not
rewrite the federation path, normalize or decompress the request body, parse and
re-encode JSON, or strip the signature headers. Forward the raw bytes with
`Content-Type`, `Content-Digest`, `Date`, `Signature-Input`, `Signature`, and the
`X-MAIL-Federation-*` headers intact. Plaintext public exposure is unsupported;
terminate trusted TLS at the proxy and keep its application hop private.

## 5. Verify discovery and exchange a message

From outside each deployment, verify that discovery is public and contains only
public key material:

```bash
curl -fsS https://mail-a.example.com/.well-known/mail-federation
curl -fsS https://mail-b.example.com/.well-known/mail-federation
```

Log in to server A as a local user, compose a draft, and address it to a known
server-B user:

```bash
export MAIL_SERVER=https://mail-a.example.com
export MAIL_ADDRESS=user:dummy@mail-a.example.com
export MAIL_PASSWORD={server-a-user-password}
uv run mail login
export MAIL_TOKEN={returned-access-token}
uv run mail compose "Federation test" "Signed delivery from server A"
uv run mail send {draft-id} user:dummy@mail-b.example.com
```

Log in to B as that user and inspect its inbox. A successful peer `202` is
followed by local daemon delivery. A terminal failure instead produces a local
DSN in A's sender inbox with the failure code and attempt history.

## 6. Rotate a key with overlap

First print the old public record, save it as the sole item in a JSON array at
`/etc/mail/server-a/overlap.json`, then generate the replacement at a new path:

```bash
uv run mail-federation-key inspect /etc/mail/server-a/federation.pem \
  --key-id server-a-2026-09 --json
uv run mail-federation-key generate /etc/mail/server-a/federation-2026-12.pem \
  --key-id server-a-2026-12
```

The overlap file must look like this:

```json
[
  {"key_id": "server-a-2026-09", "algorithm": "ed25519", "public_key": "..."}
]
```

Update server A to use the new private key and key ID while advertising the old
public record:

```env
MAIL_FEDERATION_KEY_ID=server-a-2026-12
MAIL_FEDERATION_PRIVATE_KEY_FILE=/etc/mail/server-a/federation-2026-12.pem
MAIL_FEDERATION_OVERLAP_PUBLIC_KEYS_FILE=/etc/mail/server-a/overlap.json
```

Restart A and verify its manifest advertises both IDs. Peers that encounter the
new signing key force one manifest refresh. Keep the old public key advertised
for at least the maximum configured discovery TTL (900 seconds is the v1 cap)
and until old in-flight traffic has settled. Then remove the overlap variable,
restart, verify only the new ID remains, and securely archive or destroy the old
private key according to local policy.

## 7. Inspect and retry dead letters

The supported user-visible record is the sender's outbox plus one DSN per failed
recipient. Server logs add the destination, envelope ID, attempt count/status,
next-attempt time, and terminal failure code without logging bodies or peer error
text.

For backend-level inspection, stop the server or use a read-only SQLite
connection and inspect `federation_outbound`, `message_delivery_targets`, and
`bounce_emissions`. Memory deployments persist the corresponding JSON
collections at checkpoints. Do not edit either backend by hand.

For example, with the server stopped:

```bash
sqlite3 -readonly ~/.mail-swarms/deployments/server-a/mail.db \
  "SELECT envelope_id, destination_host, status, next_attempt_at \
   FROM federation_outbound WHERE status = 'dead_letter';"
```

Federation v1 has no in-place dead-letter requeue API: retry by sending the
original draft again, which creates a new message/envelope and an independent
auditable attempt history. This avoids mutating a terminal record or duplicating
its DSN.

## 8. Disable federation safely

Set `MAIL_FEDERATION_ENABLED=false` and restart gracefully. The server stops the
worker, rejects new remote-recipient sends with `503`, and returns `404` from
discovery and signed ingress. Local sends and local daemon delivery continue.
Queued, completed, and dead-letter records remain in the backend; disabling does
not delete or rewrite them. Re-enable with the same identity/key configuration
to resume pending work.

## See also

- [Configuration](../references/configuration.md)
- [Federation Key CLI](../references/federation-key-cli.md)
- [Security Model](../explanations/security-model.md)
- [Delivery Model](../explanations/delivery-model.md)
- [Storage Backends](../references/storage-backends.md)
