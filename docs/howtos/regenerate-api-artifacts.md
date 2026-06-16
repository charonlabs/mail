# Regenerate API Artifacts

Status: stub

## Goal

How to refresh generated API or documentation artifacts after protocol, router,
or model changes.

## Starting Point

The reader changed FastAPI routes, protocol models, or generated documentation
inputs.

## Source Material

- `scripts/generate_openapi.py`
- `scripts/build_llms_txt.py`
- `scripts/build_third_party_licenses.py`
- `spec/openapi.yaml`
- `llms.txt`
- `THIRD_PARTY_NOTICES.md`

## Steps to Cover

1. Regenerate OpenAPI output.
2. Validate OpenAPI drift tests.
3. Rebuild `llms.txt` when docs or specs change.
4. Rebuild third-party license notices when dependencies change.
5. Review diffs before committing generated files.

## Validation

Contract tests pass and generated files only contain expected changes.
