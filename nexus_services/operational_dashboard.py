"""Read-only projections of canonical OperationalJournal data for the command center."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from nexus_services.runtime_contracts import OperationalJournal, TaskRecord, TaskStatus


CANONICAL_TASK_STATUSES = tuple(status.value for status in TaskStatus)
_ACTIVE_STATUSES = {
    TaskStatus.PLANNED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.WAITING_APPROVAL,
    TaskStatus.WAITING_HUMAN,
    TaskStatus.EXECUTED,
}


def _decode(value: Optional[str], default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _task_view(task: TaskRecord) -> Dict[str, Any]:
    metadata = task.metadata or {}
    return {
        "task_id": task.task_id,
        "mission_id": task.mission_id,
        "task_type": task.task_type,
        "agent": metadata.get("agent"),
        "status": task.status.value,
        "priority": task.priority,
        "execution_mode": task.execution_mode,
        "correlation_id": task.correlation_id,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "executed_at": task.completed_at if task.status in (
            TaskStatus.EXECUTED, TaskStatus.VERIFIED,
        ) else None,
        "verified_at": task.verified_at,
        "success_criteria": metadata.get("success_criteria"),
        "result": task.result,
        "error": task.error,
    }


def _mission_view(mission: Dict[str, Any], tasks: List[TaskRecord]) -> Dict[str, Any]:
    verified_count = sum(task.status == TaskStatus.VERIFIED for task in tasks)
    active_tasks = sorted(
        (task for task in tasks if task.status in _ACTIVE_STATUSES),
        key=lambda task: (task.updated_at, task.created_at),
        reverse=True,
    )
    current_task = active_tasks[0] if active_tasks else None
    count = len(tasks)
    return {
        "mission_id": mission["mission_id"],
        "objective": mission["objective"],
        "status": mission["status"],
        "session_id": mission.get("session_id"),
        "correlation_id": mission.get("correlation_id"),
        "created_at": mission["created_at"],
        "updated_at": mission["updated_at"],
        "current_task_id": current_task.task_id if current_task else None,
        "progress": {
            "verified_tasks": verified_count,
            "total_tasks": count,
            "ratio": verified_count / count if count else 0.0,
        },
        "task_counts": {
            status: sum(task.status.value == status for task in tasks)
            for status in CANONICAL_TASK_STATUSES
        },
    }


def _decode_row(row: Dict[str, Any], columns: Dict[str, str]) -> Dict[str, Any]:
    result = dict(row)
    for column, output in columns.items():
        if column in result:
            result[output] = _decode(result.pop(column), {})
    return result


def _recent_records(
    journal: OperationalJournal,
    table: str,
    **filters: Any,
) -> List[Dict[str, Any]]:
    return journal.list_records(table, newest_first=True, **filters)


def _latest_activity(journal: OperationalJournal) -> Optional[Dict[str, Any]]:
    events = _recent_records(journal, "task_events", limit=1)
    if not events:
        return None
    event = events[0]
    return {
        "event_id": event["event_id"],
        "task_id": event["task_id"],
        "mission_id": event["mission_id"],
        "event_type": event["event_type"],
        "status": event["status"],
        "occurred_at": event["occurred_at"],
        "source": event["source"],
        "actor": event["actor"],
        "details": _decode(event["details_json"], {}),
        "error": event["error"],
    }


def dashboard_overview(journal: OperationalJournal) -> Dict[str, Any]:
    sessions = journal.list_runtime_sessions(limit=100)
    active_session = next(
        (
            session for session in sessions
            if session["status"] in {"STARTING", "BOOTING", "RUNNING"}
        ),
        None,
    )
    tasks = journal.list_tasks(limit=None)
    tasks_by_mission: Dict[Optional[str], List[TaskRecord]] = {}
    for task in tasks:
        tasks_by_mission.setdefault(task.mission_id, []).append(task)
    missions = [
        _mission_view(mission, tasks_by_mission.get(mission["mission_id"], []))
        for mission in journal.list_missions(limit=None)
    ]
    latest_activity = _latest_activity(journal)
    return {
        "runtime": {
            "active_session": active_session,
            "latest_session": sessions[0] if sessions else None,
            "last_activity": latest_activity,
        },
        "missions": missions,
        "tasks": [_task_view(task) for task in tasks],
        "timeline": [
            {
                "event_id": event["event_id"],
                "mission_id": event["mission_id"],
                "task_id": event["task_id"],
                "event_type": event["event_type"],
                "status": event["status"],
                "source": event["source"],
                "actor": event["actor"],
                "occurred_at": event["occurred_at"],
                "details": _decode(event["details_json"], {}),
                "error": event["error"],
            }
            for event in _recent_records(journal, "task_events", limit=100)
        ],
        "execution_attempts": [
            _decode_row(row, {"result_json": "result", "metadata_json": "metadata"})
            for row in _recent_records(journal, "execution_attempts", limit=100)
        ],
        "tool_calls": [
            _decode_row(row, {
                "request_json": "request", "response_json": "response",
                "metadata_json": "metadata",
            })
            for row in _recent_records(journal, "tool_calls", limit=100)
        ],
        "proofs": [
            _decode_row(row, {
                "metadata_json": "metadata",
                "verification_json": "verification",
            })
            for row in _recent_records(journal, "proofs", limit=100)
        ],
        "failures": [
            _decode_row(row, {"metadata_json": "metadata"})
            for row in _recent_records(journal, "failures", limit=100)
        ],
        "recovery_actions": [
            _decode_row(row, {
                "result_json": "result", "metadata_json": "metadata",
            })
            for row in _recent_records(journal, "recovery_actions", limit=100)
        ],
        "waiting_human_tasks": [
            _task_view(task) for task in tasks
            if task.status == TaskStatus.WAITING_HUMAN
        ],
        "outcomes": [
            _decode_row(row, {
                "result_json": "result", "metadata_json": "metadata",
            })
            for row in _recent_records(journal, "outcomes", limit=100)
        ],
    }


def mission_detail(journal: OperationalJournal, mission_id: str) -> Optional[Dict[str, Any]]:
    mission = journal.get_record("missions", mission_id)
    if mission is None:
        return None
    tasks = journal.list_tasks_for_mission(mission_id)
    view = _mission_view(mission, tasks)
    view["metadata"] = _decode(mission.get("metadata_json"), {})
    view["tasks"] = [_task_view(task) for task in tasks]
    view["timeline"] = [
        {
            "event_id": event["event_id"],
            "task_id": event["task_id"],
            "event_type": event["event_type"],
            "status": event["status"],
            "source": event["source"],
            "actor": event["actor"],
            "occurred_at": event["occurred_at"],
            "details": _decode(event["details_json"], {}),
            "error": event["error"],
        }
        for event in _recent_records(journal, "task_events", mission_id=mission_id, limit=500)
    ]
    for table, json_columns in (
        ("execution_attempts", {"result_json": "result", "metadata_json": "metadata"}),
        ("tool_calls", {
            "request_json": "request", "response_json": "response",
            "metadata_json": "metadata",
        }),
        ("proofs", {"metadata_json": "metadata", "verification_json": "verification"}),
        ("failures", {"metadata_json": "metadata"}),
        ("recovery_actions", {"result_json": "result", "metadata_json": "metadata"}),
        ("outcomes", {"result_json": "result", "metadata_json": "metadata"}),
    ):
        view[table] = [
            _decode_row(row, json_columns)
            for row in _recent_records(journal, table, mission_id=mission_id, limit=500)
        ]
    return view


def task_detail(journal: OperationalJournal, task_id: str) -> Optional[Dict[str, Any]]:
    task = journal.get_task(task_id)
    if task is None:
        return None
    view = _task_view(task)
    view["payload"] = task.payload
    view["metadata"] = task.metadata
    view["proof"] = task.proof
    if task.mission_id:
        mission = journal.get_record("missions", task.mission_id)
        view["mission_objective"] = mission["objective"] if mission else None
    for table, json_columns in (
        ("task_events", {"details_json": "details"}),
        ("task_steps", {"metadata_json": "metadata", "result_json": "result"}),
        ("agent_actions", {
            "input_json": "input", "result_json": "result", "metadata_json": "metadata",
        }),
        ("decisions", {"options_json": "options"}),
        ("tool_calls", {
            "request_json": "request", "response_json": "response",
            "metadata_json": "metadata",
        }),
        ("execution_attempts", {"result_json": "result", "metadata_json": "metadata"}),
        ("failures", {"metadata_json": "metadata"}),
        ("recovery_actions", {"result_json": "result", "metadata_json": "metadata"}),
        ("approvals", {"metadata_json": "metadata"}),
        ("proofs", {"metadata_json": "metadata", "verification_json": "verification"}),
        ("observations", {"data_json": "data", "metadata_json": "metadata"}),
        ("outcomes", {"result_json": "result", "metadata_json": "metadata"}),
    ):
        view[table] = [
            _decode_row(row, json_columns)
            for row in _recent_records(journal, table, task_id=task_id, limit=500)
        ]
    return view
