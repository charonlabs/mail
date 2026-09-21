# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Shared human-readable delivery-status notification rendering."""

from mail_protocol.core.dsn import MAILDSN
from mail_protocol.core.messages import MAILMessage
from pydantic import ValidationError


def print_dsn_summary(message: MAILMessage) -> bool:
    """Print a safe DSN summary when structured metadata is present."""

    value = message.metadata.get("dsn")
    if not isinstance(value, dict):
        return False
    try:
        dsn = MAILDSN.model_validate(value)
    except ValidationError:
        return False

    print("=== Delivery Failure ===")
    print(f"Failure Code: {dsn.failure_code}")
    print(f"Reason: {dsn.failure_reason}")
    print(f"Original Message ID: {dsn.original_message_id}")
    print(f"Failed Recipient: {dsn.failed_recipient}")
    print(f"Failure Location: {dsn.failed_at}")
    if dsn.attempt_count is not None:
        print(f"Attempt Count: {dsn.attempt_count}")
    if dsn.attempt_timestamps is not None:
        print(
            "Attempt Timestamps: "
            + ", ".join(timestamp.isoformat() for timestamp in dsn.attempt_timestamps)
        )
    print(f"Failed At: {dsn.timestamp.isoformat()}")
    return True
