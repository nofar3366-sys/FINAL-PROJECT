from collections.abc import Callable

from .availability import (
    check_class_availability_skill,
    get_class_availability_skill,
)
from .member_status import get_member_status_skill
from .scheduling import schedule_class_skill, schedule_recurring_sessions_skill


SKILL_FUNCTIONS: dict[str, Callable[..., dict[str, object]]] = {
    "check_class_availability_skill": check_class_availability_skill,
    "get_class_availability_skill": get_class_availability_skill,
    "get_member_status_skill": get_member_status_skill,
    "schedule_class_skill": schedule_class_skill,
    "schedule_recurring_sessions_skill": schedule_recurring_sessions_skill,
}

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_class_availability_skill",
            "description": (
                "Find classes for a date and trainer specialty with remaining capacity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "specialty": {"type": "string"},
                },
                "required": ["date", "specialty"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_class_skill",
            "description": "Create one class after manager authorization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trainer_id": {"type": "integer", "minimum": 1},
                    "date_time": {
                        "type": "string",
                        "description": "ISO local date and time",
                    },
                    "capacity": {"type": "integer", "minimum": 1},
                },
                "required": ["trainer_id", "date_time", "capacity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_class_availability_skill",
            "description": "Check current capacity for a workout session.",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "integer", "minimum": 1}},
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_member_status_skill",
            "description": (
                "Get membership expiry, active state, and credit balance. "
                "The application must authorize access before calling this skill."
            ),
            "parameters": {
                "type": "object",
                "properties": {"member_id": {"type": "integer", "minimum": 1}},
                "required": ["member_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_recurring_sessions_skill",
            "description": "Create weekly workout sessions for one active trainer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trainer_name": {"type": "string"},
                    "title": {"type": "string"},
                    "weekday": {"type": "string"},
                    "start_time": {"type": "string"},
                    "max_capacity": {"type": "integer", "minimum": 1},
                    "occurrences": {"type": "integer", "minimum": 1, "maximum": 12},
                    "duration_minutes": {"type": "integer", "minimum": 1},
                },
                "required": [
                    "trainer_name",
                    "title",
                    "weekday",
                    "start_time",
                    "max_capacity",
                ],
            },
        },
    },
]


def execute_skill(name: str, arguments: dict[str, object]) -> dict[str, object]:
    """Execute an allow-listed skill; authorization remains a controller concern."""

    try:
        skill = SKILL_FUNCTIONS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown AI skill: {name}") from exc
    return skill(**arguments)
