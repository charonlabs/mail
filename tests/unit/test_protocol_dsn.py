# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest
from mail_protocol.core import MAILDSN, FailedAt, FailureCode
from pydantic import ValidationError

NOW = datetime(2026, 9, 11, 21, 47, 23, tzinfo=UTC)
LATER = NOW + timedelta(seconds=30)
UUID = "550e8400-e29b-41d4-a716-446655440000"


def _dsn_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "failure_code": "host_unreachable",
        "failure_reason": "destination host could not be reached",
        "original_message_id": UUID,
        "failed_recipient": "bob@village@example.com",
        "failed_at": "in_transit",
        "timestamp": NOW,
        "attempt_count": 2,
        "attempt_timestamps": [NOW, LATER],
    }
    payload.update(overrides)
    return payload


def test_dsn_round_trips_through_dump_and_validate() -> None:
    dsn = MAILDSN.model_validate(_dsn_payload())
    assert MAILDSN.model_validate(dsn.model_dump()) == dsn


def test_dsn_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MAILDSN.model_validate(_dsn_payload(unexpected="field"))


def test_dsn_rejects_attempt_timestamps_without_attempt_count() -> None:
    with pytest.raises(ValidationError):
        MAILDSN.model_validate(
            _dsn_payload(attempt_count=None, attempt_timestamps=[NOW])
        )


def test_dsn_rejects_attempt_timestamps_with_wrong_length() -> None:
    with pytest.raises(ValidationError):
        MAILDSN.model_validate(_dsn_payload(attempt_count=2, attempt_timestamps=[NOW]))


def test_dsn_rejects_origin_failure_with_attempt_count() -> None:
    with pytest.raises(ValidationError):
        MAILDSN.model_validate(
            _dsn_payload(
                failed_at="origin",
                attempt_count=1,
                attempt_timestamps=None,
            )
        )


@pytest.mark.parametrize("failure_code", get_args(FailureCode))
def test_dsn_accepts_every_failure_code(failure_code: str) -> None:
    assert MAILDSN.model_validate(_dsn_payload(failure_code=failure_code))


@pytest.mark.parametrize("failed_at", get_args(FailedAt))
def test_dsn_accepts_every_failed_at(failed_at: str) -> None:
    payload = _dsn_payload(failed_at=failed_at)
    if failed_at == "origin":
        payload["attempt_count"] = None
        payload["attempt_timestamps"] = None
    assert MAILDSN.model_validate(payload)
