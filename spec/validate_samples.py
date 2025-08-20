import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def try_import_jsonschema():
    try:
        import jsonschema  # type: ignore
        return jsonschema
    except Exception:
        return None


def make_uuid():
    import uuid

    return str(uuid.uuid4())


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def sample_mail_request_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "message": {
            "task_id": task_id,
            "request_id": make_uuid(),
            "sender": {"address_type": "user", "address": "user_123"},
            "recipient": {"address_type": "agent", "address": "supervisor"},
            "subject": "New Message",
            "body": "What is the weather today?",
        },
        "msg_type": "request",
    }


def sample_broadcast_complete_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "message": {
            "task_id": task_id,
            "broadcast_id": make_uuid(),
            "sender": {"address_type": "agent", "address": "supervisor"},
            "recipients": [
                {"address_type": "agent", "address": "all"}
            ],
            "subject": "Task complete",
            "body": "Done.",
        },
        "msg_type": "broadcast_complete",
    }


def sample_interswarm_request_wrapper():
    # payload is a MAILRequest (not the outer MAILMessage)
    task_id = make_uuid()
    payload = {
        "task_id": task_id,
        "request_id": make_uuid(),
        "sender": {"address_type": "agent", "address": "supervisor@swarm-a"},
        "recipient": {"address_type": "agent", "address": "weather@swarm-b"},
        "subject": "Interswarm Message",
        "body": "Forecast please",
        "sender_swarm": "swarm-a",
        "recipient_swarm": "swarm-b",
    }
    return {
        "message_id": make_uuid(),
        "source_swarm": "swarm-a",
        "target_swarm": "swarm-b",
        "timestamp": iso_now(),
        "payload": payload,
        "msg_type": "request",
        "metadata": {"expect_response": True},
    }


def sample_mail_response_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "message": {
            "task_id": task_id,
            "request_id": make_uuid(),
            "sender": {"address_type": "agent", "address": "weather"},
            "recipient": {"address_type": "agent", "address": "supervisor"},
            "subject": "Re: Forecast",
            "body": "Sunny with light winds.",
        },
        "msg_type": "response",
    }


def sample_mail_broadcast_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "message": {
            "task_id": task_id,
            "broadcast_id": make_uuid(),
            "sender": {"address_type": "system", "address": "system"},
            "recipients": [
                {"address_type": "agent", "address": "supervisor"},
                {"address_type": "agent", "address": "weather"}
            ],
            "subject": "Action Complete: get_weather_forecast",
            "body": "The action result payload...",
        },
        "msg_type": "broadcast",
    }


def sample_mail_interrupt_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "message": {
            "task_id": task_id,
            "interrupt_id": make_uuid(),
            "sender": {"address_type": "agent", "address": "supervisor"},
            "recipients": [
                {"address_type": "agent", "address": "weather"}
            ],
            "subject": "Pause",
            "body": "Stop processing current task.",
        },
        "msg_type": "interrupt",
    }


def sample_interswarm_response_wrapper():
    task_id = make_uuid()
    payload = {
        "task_id": task_id,
        "request_id": make_uuid(),
        "sender": {"address_type": "agent", "address": "weather@swarm-b"},
        "recipient": {"address_type": "agent", "address": "supervisor@swarm-a"},
        "subject": "Re: Interswarm Message",
        "body": "Sunny on remote swarm.",
        "sender_swarm": "swarm-b",
        "recipient_swarm": "swarm-a",
    }
    return {
        "message_id": make_uuid(),
        "source_swarm": "swarm-b",
        "target_swarm": "swarm-a",
        "timestamp": iso_now(),
        "payload": payload,
        "msg_type": "response",
        "metadata": {"expect_response": False},
    }


def sample_invalid_mismatch_message():
    # msg_type says response but content is a request
    obj = sample_mail_request_message()
    obj["msg_type"] = "response"
    return obj


def main():
    root = Path(__file__).resolve().parent
    core_schema = load_json(root / "MAIL-core.schema.json")
    inter_schema = load_json(root / "MAIL-interswarm.schema.json")

    jsonschema = try_import_jsonschema()
    samples = [
        ("MAILMessage request", sample_mail_request_message(), core_schema, True),
        ("MAILMessage response", sample_mail_response_message(), core_schema, True),
        ("MAILMessage broadcast", sample_mail_broadcast_message(), core_schema, True),
        ("MAILMessage interrupt", sample_mail_interrupt_message(), core_schema, True),
        ("MAILMessage broadcast_complete", sample_broadcast_complete_message(), core_schema, True),
        ("MAILInterswarm request wrapper", sample_interswarm_request_wrapper(), inter_schema, True),
        ("MAILInterswarm response wrapper", sample_interswarm_response_wrapper(), inter_schema, True),
    ]

    if jsonschema is None:
        print("jsonschema not installed; performing basic structure checks only\n")
        # Basic checks: required keys exist
        for name, obj, _schema, _expect_valid in samples:
            ok = all(k in obj for k in ("id", "timestamp", "message")) if name.startswith("MAILMessage") else all(
                k in obj for k in ("message_id", "source_swarm", "target_swarm", "payload"))
            print(f"[BASIC] {name}: {'OK' if ok else 'MISSING KEYS'}")
        sys.exit(0)

    # Full validation
    print("Using jsonschema", jsonschema.__version__)
    Draft = getattr(jsonschema, "Draft202012Validator", None)
    if Draft is None:
        print("jsonschema does not support Draft 2020-12 validator; attempting generic validate()\n")
        from jsonschema import validate
        for name, obj, schema in samples:
            try:
                validate(instance=obj, schema=schema)
                print(f"[VALID] {name}")
            except Exception as e:
                print(f"[INVALID] {name}: {e}")
        return

    # Resolve $refs relative to spec directory
    # Build a resolver rooted at spec/ for local $ref resolution
    # Avoid any network fetch by providing a local store for $id references
    store = {}
    if isinstance(core_schema.get("$id"), str):
        store[core_schema["$id"]] = core_schema
    if isinstance(inter_schema.get("$id"), str):
        store[inter_schema["$id"]] = inter_schema
    store[(root / "MAIL-core.schema.json").as_uri()] = core_schema
    store[(root / "MAIL-interswarm.schema.json").as_uri()] = inter_schema

    resolver = jsonschema.RefResolver(base_uri=(root.as_uri() + "/"), referrer=core_schema, store=store)
    for name, obj, schema, expect_valid in samples:
        try:
            Draft(schema, resolver=resolver).validate(obj)
            if expect_valid:
                print(f"[VALID] {name}")
        except Exception as e:
            print(f"[INVALID] {name}: {e}")

    # Also validate concrete example files under spec/examples
    examples_dir = root / "examples"
    if examples_dir.exists():
        for p in sorted(examples_dir.glob("*.json")):
            try:
                data = load_json(p)
                schema = inter_schema if p.name.startswith("interswarm_") else core_schema
                Draft(schema, resolver=resolver).validate(data)
                print(f"[VALID] example {p.name}")
            except Exception as e:
                print(f"[INVALID] example {p.name}: {e}")


if __name__ == "__main__":
    main()
