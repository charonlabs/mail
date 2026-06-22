# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from pathlib import Path


def resolve_body(body: str | None, body_file: str | None) -> str:
    """
    Resolve a message body from the mutually exclusive ``body`` (inline) and
    ``body_file`` (path) CLI arguments used by ``compose``.

    Exactly one of the two must be supplied. When ``body_file`` is given, its
    contents are read as UTF-8 text. Raises ``ValueError`` (surfaced by the
    CLI as a command error) when neither or both are provided, or when the
    file cannot be read.
    """

    if body is not None and body_file is not None:
        raise ValueError("provide either a body argument or --body-file, not both")
    if body is not None:
        return body
    if body_file is not None:
        try:
            return Path(body_file).read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"could not read body file {body_file!r}: {e}")
    raise ValueError("a message body is required: pass it inline or via --body-file")


def resolve_optional_body(body: str | None, body_file: str | None) -> str | None:
    """
    Variant of :func:`resolve_body` for partial-update commands (draft-edit)
    where the body is optional. Returns ``None`` when neither argument is
    supplied (meaning "leave the body unchanged"); otherwise behaves like
    :func:`resolve_body`, including the "not both" guard.
    """

    if body is None and body_file is None:
        return None
    return resolve_body(body, body_file)
