from __future__ import annotations

from typing import Any

from apps.node_mgmt.utils.installer_schema import normalize_failure, normalize_installer_action, normalize_overall_status


"""Shared normalization helpers for generic task result envelopes."""

EXPECTED_INSTALLER_STEPS = [
    "fetch_session",
    "prepare_dirs",
    "download",
    "extract",
    "write_config",
    "install",
]


def _extract_latest_failure_from_steps(steps):
    """Return the most recent normalized failure stored in step details."""
    if not isinstance(steps, list):
        return None

    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        details = step.get("details")
        if isinstance(details, dict) and details.get("failure"):
            return details.get("failure")

    return None


def _normalize_step_message(step_message):
    if isinstance(step_message, str):
        stripped_message = step_message.strip()
        if stripped_message:
            return step_message
    return "--"


def _is_installer_event_step(step):
    details = step.get("details") if isinstance(step, dict) else None
    return isinstance(details, dict) and details.get("installer_event") is True


def _canonical_installer_step(step):
    details = step.get("details") if isinstance(step.get("details"), dict) else {}
    return normalize_installer_action(details.get("raw_step") or step.get("action"))


def _dedupe_installer_events(installer_steps):
    latest_by_action = {}
    order = []

    for step in installer_steps:
        action = _canonical_installer_step(step)
        if action not in order:
            order.append(action)
        latest_by_action[action] = {
            **step,
            "action": action,
        }

    return [latest_by_action[action] for action in order if action in latest_by_action]


def _build_installer_summary(steps, overall_status=None):
    if not isinstance(steps, list):
        return None

    looks_like_controller_install = any(
        isinstance(step, dict)
        and (step.get("action") in {"run", "connectivity_check"} or _is_installer_event_step(step))
        for step in steps
    )
    if not looks_like_controller_install:
        return None

    installer_steps = [step for step in steps if isinstance(step, dict) and _is_installer_event_step(step)]
    deduped_steps = _dedupe_installer_events(installer_steps)
    deduped_core_steps = [step for step in deduped_steps if step.get("action") in EXPECTED_INSTALLER_STEPS]
    observed_count = len(installer_steps)
    duplicate_count = max(observed_count - len(deduped_steps), 0)
    completed_steps = [
        step.get("action")
        for step in deduped_core_steps
        if step.get("status") == "success" and step.get("action") in EXPECTED_INSTALLER_STEPS
    ]
    observed_actions = {step.get("action") for step in deduped_core_steps}
    missing_steps = [step for step in EXPECTED_INSTALLER_STEPS if step not in observed_actions]
    last_step = deduped_core_steps[-1] if deduped_core_steps else None
    connectivity_step = next(
        (
            step
            for step in reversed(steps)
            if isinstance(step, dict) and step.get("action") == "connectivity_check"
        ),
        None,
    )

    anomalies = []
    state = "installer_events_complete"
    if not installer_steps:
        state = "no_installer_events"
        anomalies.append(state)
    elif missing_steps or any(step.get("status") in {"error", "timeout"} for step in deduped_core_steps):
        state = "incomplete_installer_events"
        anomalies.append(state)
    elif connectivity_step and connectivity_step.get("status") == "running":
        state = "installer_success_connectivity_pending"
        anomalies.append(state)
    elif connectivity_step and connectivity_step.get("status") in {"error", "timeout"}:
        state = "installer_success_connectivity_timeout"
        anomalies.append(state)
    elif overall_status == "success":
        state = "installer_success_connectivity_confirmed"

    if duplicate_count:
        anomalies.insert(0, "duplicated_events")

    return {
        "state": state,
        "expected_steps": EXPECTED_INSTALLER_STEPS,
        "expected_count": len(EXPECTED_INSTALLER_STEPS),
        "observed_count": observed_count,
        "completed_steps": completed_steps,
        "completed_count": len(completed_steps),
        "missing_steps": missing_steps,
        "duplicate_count": duplicate_count,
        "last_step": last_step.get("action") if last_step else None,
        "last_status": last_step.get("status") if last_step else None,
        "anomalies": anomalies,
        "steps": deduped_core_steps,
    }


def normalize_task_details(details=None, *, message=None, error=None):
    """Preserve legacy detail keys while attaching normalized failure data."""
    prepared_details = details.copy() if isinstance(details, dict) else {}
    failure = normalize_failure(message=message, error=error, details=prepared_details)
    if failure:
        prepared_details["failure"] = failure
        if failure.get("type") == "timeout":
            prepared_details["timeout"] = True
    return prepared_details or None


def apply_result_envelope(result=None, *, overall_status=None, final_message=None, failure=None):
    """Guarantee top-level task result fields and normalized terminal failure."""
    prepared_result = result.copy() if isinstance(result, dict) else {}
    steps = prepared_result.get("steps")
    prepared_result["steps"] = steps if isinstance(steps, list) else []

    if overall_status is not None:
        prepared_result["overall_status"] = normalize_overall_status(overall_status)

    if final_message is not None:
        prepared_result["final_message"] = final_message

    normalized_failure = normalize_failure(
        message=(failure or {}).get("message") if isinstance(failure, dict) else None,
        error=(failure or {}).get("raw_error") if isinstance(failure, dict) else None,
        details=failure,
    )

    current_status = prepared_result.get("overall_status")
    if current_status in {"error", "timeout", "cancelled"} and normalized_failure:
        prepared_result["failure"] = normalized_failure
    elif current_status == "success":
        prepared_result.pop("failure", None)

    return prepared_result


def normalize_task_result_for_read(result=None):
    """Normalize historical task result payloads before returning them to readers."""
    prepared_result = apply_result_envelope(
        result,
        overall_status=(result or {}).get("overall_status") if isinstance(result, dict) else None,
        final_message=(result or {}).get("final_message") if isinstance(result, dict) else None,
        failure=(result or {}).get("failure") if isinstance(result, dict) else None,
    )

    steps = prepared_result.get("steps", [])
    normalized_steps = []
    latest_failure = None

    for step in steps:
        if not isinstance(step, dict):
            continue

        step_details_raw = step.get("details") if isinstance(step.get("details"), dict) else None
        step_status = step.get("status") or "waiting"
        step_message = _normalize_step_message(step.get("message"))
        should_attach_failure = step_status in {"error", "timeout"} or (step_details_raw or {}).get("error_type") == "timeout"
        step_details = normalize_task_details(
            step_details_raw,
            message=step_message if should_attach_failure else None,
            error=step_details_raw.get("error") if step_details_raw else None,
        )

        normalized_step = {
            "action": step.get("action") or "unknown",
            "status": step_status,
            "message": step_message,
            "timestamp": step.get("timestamp") or "",
        }
        if step_details:
            normalized_step["details"] = step_details
            if step_details.get("failure"):
                latest_failure = step_details.get("failure")

        normalized_steps.append(normalized_step)

    prepared_result["steps"] = normalized_steps

    installer_progress = prepared_result.get("installer_progress")
    if not isinstance(installer_progress, dict):
        prepared_result["installer_progress"] = None

    latest_failure = latest_failure or _extract_latest_failure_from_steps(prepared_result.get("steps"))

    if latest_failure and prepared_result.get("overall_status") in {"error", "timeout", "cancelled"}:
        prepared_result["failure"] = latest_failure

    installer_summary = _build_installer_summary(
        normalized_steps,
        overall_status=prepared_result.get("overall_status"),
    )
    if installer_summary:
        prepared_result["installer_summary"] = installer_summary
    else:
        prepared_result.pop("installer_summary", None)

    return prepared_result
