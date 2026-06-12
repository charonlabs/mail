# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
spec/openapi.yaml is the published API contract. It is generated from
the FastAPI app by scripts/generate_openapi.py; this test fails when
the app and the committed document diverge, so an API change can't
ship without the spec being regenerated deliberately.
"""

from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).resolve().parents[2] / "spec" / "openapi.yaml"


def test_openapi_schema_matches_committed_spec() -> None:
    from mail_server.server import app

    generated = app.openapi()
    committed = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    assert generated == committed, (
        "spec/openapi.yaml no longer matches the FastAPI app. If the API "
        "change is intentional, regenerate the document with "
        "`uv run python scripts/generate_openapi.py` and commit it; "
        "otherwise revert the app change."
    )
