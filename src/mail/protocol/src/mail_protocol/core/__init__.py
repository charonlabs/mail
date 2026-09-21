# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""Convenience re-exports for the ``mail_protocol.core`` package.

Modules in ``mail_protocol.core.*`` remain the canonical import paths;
this ``__init__`` surfaces a small number of Bounces v1 public types so
callers can write ``from mail_protocol.core import MAILDSN`` rather
than the deeper ``from mail_protocol.core.dsn import MAILDSN``. Federation
and other domains continue to be imported at their deeper paths per the
existing package convention.
"""

from mail_protocol.core.dsn import MAILDSN, MAILDSNFailureCode

__all__ = [
    "MAILDSN",
    "MAILDSNFailureCode",
]
