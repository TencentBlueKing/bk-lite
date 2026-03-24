from datetime import datetime


def now_iso():
    return datetime.now().isoformat()


def build_step(action, status, message, timestamp=None, details=None):
    step = {
        "action": action,
        "status": status,
        "message": message,
        "timestamp": timestamp or now_iso(),
    }
    if details:
        step["details"] = details
    return step


def clone_steps(step_items, timestamp=None):
    prepared_timestamp = timestamp or now_iso()
    prepared_steps = []
    for step in step_items:
        prepared_step = step.copy()
        prepared_step.setdefault("timestamp", prepared_timestamp)
        if "details" in prepared_step and isinstance(prepared_step["details"], dict):
            prepared_step["details"] = prepared_step["details"].copy()
        prepared_steps.append(prepared_step)
    return prepared_steps


def append_steps(result, step_items):
    steps = result.get("steps", [])
    steps.extend(step_items)
    result["steps"] = steps
    return steps


def append_step(result, action, status, message, timestamp=None, details=None):
    step = build_step(action, status, message, timestamp=timestamp, details=details)
    append_steps(result, [step])
    return step


def update_last_running_step(result, status, message, details=None, timestamp=None):
    steps = result.get("steps", [])
    if steps and steps[-1].get("status") == "running":
        steps[-1]["status"] = status
        steps[-1]["message"] = message
        steps[-1]["timestamp"] = timestamp or now_iso()
        if details:
            steps[-1]["details"] = details
        result["steps"] = steps
        return True
    return False


def update_step_by_action(
    result, action, status, message, details=None, timestamp=None
):
    steps = result.get("steps", [])
    for step in steps:
        if step.get("action") != action:
            continue
        step["status"] = status
        step["message"] = message
        step["timestamp"] = timestamp or now_iso()
        if details:
            step["details"] = details
        result["steps"] = steps
        return True
    return False


def advance_step(
    result, status, message, details=None, next_steps=None, timestamp=None
):
    prepared_timestamp = timestamp or now_iso()
    update_last_running_step(
        result,
        status,
        message,
        details=details,
        timestamp=prepared_timestamp,
    )
    if next_steps:
        append_steps(result, clone_steps(next_steps, timestamp=prepared_timestamp))
    return result.get("steps", [])
