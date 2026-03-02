import json
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path


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
    return datetime.now(UTC).isoformat()


def sample_mail_direct_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "msg_type": "direct",
        "sender": {
            "addr_type": "user",
            "address": "user_123",
        },
        "recipients": [
            {
                "addr_type": "agent",
                "address": "supervisor",
            }
        ],
        "subject": "New Message",
        "body": "What is the weather today?",
        "metadata": {},
        "task_id": task_id,
    }


def sample_task_complete_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "msg_type": "task_complete",
        "sender": {
            "addr_type": "agent",
            "address": "supervisor",
        },
        "recipients": [
            {
                "addr_type": "agent",
                "address": "all",
            }
        ],
        "subject": "Task complete",
        "body": "Done.",
        "metadata": {},
        "task_id": task_id,
    }


def sample_interswarm_request_wrapper():
    # payload is a MAILRequest (not the outer MAILMessage)
    task_id = make_uuid()
    payload = {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "msg_type": "direct",
        "sender": {
            "addr_type": "agent",
            "address": "supervisor@swarm-a",
        },
        "recipients": [
            {
                "addr_type": "agent",
                "address": "weather@swarm-b",
            }
        ],
        "subject": "Interswarm Message",
        "body": "Forecast please",
        "metadata": {},
        "task_id": task_id,
    }
    task = {
        "task_id": task_id,
        "task_owner": {
          "instance_type": "user",
          "instance_client_id": "123",
          "swarm_name": "swarm-a"
        },
        "task_contributors": [
          {
            "instance_type": "user",
            "instance_client_id": "123",
            "swarm_name": "swarm-a"
          }
        ],
        "start_time": iso_now(),
        "completed": False,
        "metadata": {},
    }
    return {
        "message_id": make_uuid(), 
        "source_swarm": "swarm-a",
        "target_swarm": "swarm-b",
        "timestamp": iso_now(), 
        "task": task,
        "payload": payload,
        "metadata": {},
    }


def sample_mail_broadcast_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "msg_type": "broadcast",
        "sender": {
            "addr_type": "system",
            "address": "system",
        },
        "recipients": [
            {
                "addr_type": "agent",
                "address": "supervisor",
            },
            {
                "addr_type": "agent",
                "address": "weather",
            }
        ],
        "subject": "Action Complete: get_weather_forecast",
        "body": "The action result payload...",
        "metadata": {},
        "task_id": task_id,
    }


def sample_mail_interrupt_message():
    task_id = make_uuid()
    return {
        "id": make_uuid(),
        "timestamp": iso_now(),
        "msg_type": "interrupt",
        "sender": {
            "addr_type": "agent",
            "address": "supervisor",
        },
        "recipients": [
            {
                "addr_type": "agent",
                "address": "weather",
            }
        ],
        "subject": "Pause",
        "body": "Stop processing current task.",
        "metadata": {},
        "task_id": task_id,
    }


def main():
    root = Path(__file__).resolve().parent
    core_schema = load_json(root / "MAIL-core.schema.json")
    inter_schema = load_json(root / "MAIL-interswarm.schema.json")

    jsonschema = try_import_jsonschema()
    samples = [
        ("MAILMessage direct", sample_mail_direct_message(), core_schema, True),
        ("MAILMessage task complete", sample_task_complete_message(), core_schema, True),
        ("MAILMessage broadcast", sample_mail_broadcast_message(), core_schema, True),
        ("MAILMessage interrupt", sample_mail_interrupt_message(), core_schema, True),
        (
            "MAILInterswarm request",
            sample_interswarm_request_wrapper(),
            inter_schema,
            True,
        ),
    ]

    if jsonschema is None:
        print("jsonschema not installed; performing basic structure checks only\n")
        # Basic checks: required keys exist
        for name, obj, _schema, _expect_valid in samples:
            ok = (
                all(k in obj for k in ("id", "timestamp", "msg_type"))
                if name.startswith("MAILMessage")
                else all(
                    k in obj
                    for k in ("message_id", "source_swarm", "target_swarm", "payload", "msg_type")
                )
            )
            print(f"[BASIC] {name}: {'OK' if ok else 'MISSING KEYS'}")
        sys.exit(0)

    # Full validation
    print("Using jsonschema", metadata.version("jsonschema"))
    Draft = getattr(jsonschema, "Draft202012Validator", None)
    if Draft is None:
        print(
            "jsonschema does not support Draft 2020-12 validator; attempting generic validate()\n"
        )
        from jsonschema import validate

        for name, obj, schema, _expect_valid in samples:
            try:
                validate(instance=obj, schema=schema)
                print(f"[VALID] {name}")
            except Exception as e:
                print(f"[INVALID] {name}: {e}")
        return

    # Resolve $refs using the 'referencing' library instead of RefResolver
    # Build a registry of local resources keyed by both $id and file URI
    try:
        from referencing import Registry, Resource  # type: ignore
        from referencing.jsonschema import DRAFT202012  # type: ignore
    except Exception:
        print("Failed to import 'referencing'; cannot build a reference registry")
        sys.exit(1)

    resources = {}

    def _resource_for(contents: dict, file_name: str):
        res = Resource.from_contents(contents, default_specification=DRAFT202012)
        # Map by declared $id if present
        _id = contents.get("$id")
        if isinstance(_id, str):
            resources[_id] = res
        # Also map by on-disk file URI for relative file refs
        resources[(root / file_name).as_uri()] = res
        return res

    _resource_for(core_schema, "MAIL-core.schema.json")
    _resource_for(inter_schema, "MAIL-interswarm.schema.json")

    registry = Registry()
    for uri, res in resources.items():
        registry = registry.with_resource(uri, res)

    for name, obj, schema, expect_valid in samples:
        try:
            Draft(schema, registry=registry).validate(obj)
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
                schema = (
                    inter_schema if p.name.startswith("interswarm_") else core_schema
                )
                Draft(schema, registry=registry).validate(data)
                print(f"[VALID] example {p.name}")
            except Exception as e:
                print(f"[INVALID] example {p.name}: {e}")


if __name__ == "__main__":
    main()
