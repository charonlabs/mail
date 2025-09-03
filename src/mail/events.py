from typing import TypedDict

class MAILEvent(TypedDict):
    """A generic event in the MAIL system."""

    timestamp: str
    """The timestamp of the event."""

    task_id: str
    """The task id of the event."""

    description: str
    """The description of the event."""