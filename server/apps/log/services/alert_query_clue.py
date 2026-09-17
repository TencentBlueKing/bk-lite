from copy import deepcopy


def freeze_log_alert_query_clue(policy, window_start=None, window_end=None) -> dict:
    """Freeze the hit-time query clue. Never re-read live Policy at display time."""
    collect_type = getattr(policy, "collect_type", None)
    return {
        "policy_id": getattr(policy, "id", None),
        "policy_name": getattr(policy, "name", None),
        "collect_type_id": getattr(policy, "collect_type_id", None),
        "collect_type_name": getattr(collect_type, "name", None) if collect_type is not None else None,
        "log_groups": deepcopy(list(getattr(policy, "log_groups", None) or [])),
        "alert_type": getattr(policy, "alert_type", None),
        "alert_name": getattr(policy, "alert_name", None),
        "alert_level": getattr(policy, "alert_level", None),
        "alert_condition": deepcopy(getattr(policy, "alert_condition", None) or {}),
        "period": deepcopy(getattr(policy, "period", None) or {}),
        "schedule": deepcopy(getattr(policy, "schedule", None) or {}),
        "show_fields": deepcopy(list(getattr(policy, "show_fields", None) or [])),
        "window_start": window_start,
        "window_end": window_end,
    }
