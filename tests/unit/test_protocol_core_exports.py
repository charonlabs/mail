# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""Verify the ``mail_protocol.core`` package's public export surface.

The core package re-exports a small number of Bounces v1 public types so
callers can write ``from mail_protocol.core import MAILDSN`` rather than
the deeper ``from mail_protocol.core.dsn import MAILDSN``. This test
pins the export list so an accidental removal would fail loudly.
"""

from __future__ import annotations

import mail_protocol.core as core
from mail_protocol.core.dsn import (
    MAILDSN as _MAILDSN_deep,
    MAILDSNFailureCode as _MAILDSNFailureCode_deep,
)


def test_mail_dsn_reexported_from_core() -> None:
    """``from mail_protocol.core import MAILDSN`` works and returns the
    same class as ``from mail_protocol.core.dsn import MAILDSN``."""
    from mail_protocol.core import MAILDSN

    assert MAILDSN is _MAILDSN_deep


def test_mail_dsn_failure_code_reexported_from_core() -> None:
    """``from mail_protocol.core import MAILDSNFailureCode`` works and
    returns the same enum as the deeper import."""
    from mail_protocol.core import MAILDSNFailureCode

    assert MAILDSNFailureCode is _MAILDSNFailureCode_deep


def test_core_dunder_all_contains_bounces_public_types() -> None:
    """The package ``__all__`` names both Bounces v1 public types.
    Guards against silent removal from the re-export list."""
    assert "MAILDSN" in core.__all__
    assert "MAILDSNFailureCode" in core.__all__
