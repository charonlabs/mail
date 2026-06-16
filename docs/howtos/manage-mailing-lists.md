# Manage Mailing Lists

Status: stub

## Goal

How to create mailing lists, inspect them, and manage subscriptions or members.

## Starting Point

The reader has credentials with permissions appropriate for the list action.

## Source Material

- `src/mail/client/src/mail_client/commands/lists.py`
- `src/mail/client/src/mail_client/commands/list_post.py`
- `src/mail/client/src/mail_client/commands/list_subscribe.py`
- `src/mail/client/src/mail_client/commands/list_member_post.py`
- `src/mail/server/src/mail_server/routers/lists.py`
- `src/mail/protocol/src/mail_protocol/core/lists.py`

## Steps to Cover

1. List available mailing lists.
2. Inspect one list by address.
3. Create a list as an admin.
4. Subscribe and unsubscribe as a user-agent.
5. Add or remove members as an admin.
6. Send a message to a list address.

## Validation

List membership changes are reflected in list lookup and list-address sends
deliver to expected recipients.
