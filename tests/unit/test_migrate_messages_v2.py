# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Tests for scripts/migrate_messages_v2.py, the MAIL 2.0 message-schema
backfill migration.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from mail_protocol.core.messages import MAILMessage

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_messages_v2.py"
_spec = importlib.util.spec_from_file_location("migrate_messages_v2", _SCRIPT)
assert _spec is not None and _spec.loader is not None
migrate = importlib.util.module_from_spec(_spec)
# Register before exec so dataclass introspection can resolve the module.
sys.modules[_spec.name] = migrate
_spec.loader.exec_module(migrate)


PRE_V2_RECORD = {
    "message_id": "55555555-5555-4555-8555-555555555555",
    "sender": "user:alice@localhost",
    "recipients": ["sage@chorus@localhost"],
    "subject": "Legacy",
    "body": "Persisted before MAIL 2.0.",
    "sent_at": "2026-06-12T09:00:00+00:00",
    "metadata": {},
}


def _write(messages_dir: Path, record: dict) -> Path:
    path = messages_dir / record["message_id"]
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    path = _write(messages, PRE_V2_RECORD)

    result = migrate.migrate_messages(messages, dry_run=True)

    assert result.scanned == 1
    assert result.migrated == 1
    assert result.already_current == 0
    # File on disk is untouched in dry-run mode.
    assert json.loads(path.read_text()) == PRE_V2_RECORD


def test_migration_backfills_and_validates(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    path = _write(messages, PRE_V2_RECORD)

    result = migrate.migrate_messages(messages, dry_run=False)
    assert result.migrated == 1

    upgraded = json.loads(path.read_text())
    assert upgraded["mail_version"] == "2.0"
    assert upgraded["tags"] == []
    # The migrated record now passes the MAIL 2.0 model contract.
    model = MAILMessage.model_validate(upgraded)
    assert model.reply_to is None


def test_existing_fields_are_preserved(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    record = dict(PRE_V2_RECORD)
    record["mail_version"] = "2.0"
    record["tags"] = ["already-tagged"]
    path = _write(messages, record)

    result = migrate.migrate_messages(messages, dry_run=False)

    assert result.migrated == 0
    assert result.already_current == 1
    assert json.loads(path.read_text())["tags"] == ["already-tagged"]


def test_idempotent_second_run_is_noop(tmp_path: Path) -> None:
    messages = tmp_path / "messages"
    messages.mkdir()
    _write(messages, PRE_V2_RECORD)

    migrate.migrate_messages(messages, dry_run=False)
    second = migrate.migrate_messages(messages, dry_run=False)

    assert second.migrated == 0
    assert second.already_current == 1


def test_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migrate.migrate_messages(tmp_path / "nope", dry_run=True)
