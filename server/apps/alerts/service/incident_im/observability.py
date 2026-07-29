from apps.core.logger import alert_logger as logger


_SAFE_FIELDS = frozenset(
    {
        "group_id",
        "incident_id",
        "operation",
        "duration_ms",
        "result",
        "error_code",
        "request_id",
        "member_count",
        "retryable",
        "joined_count",
        "failed_count",
        "invalid_count",
        "waiting_mapping_count",
        "pending_count",
        "delivering_count",
        "oldest_pending_age_seconds",
        "skip_reason",
        "status",
        "pause_reason",
    }
)
_SAFE_EVENTS = frozenset(
    {
        "incident_im_group_delivery",
        "incident_im_member_batch",
        "incident_im_reconcile",
        "incident_im_lifecycle",
        "incident_im_outbox_backlog",
    }
)


def _render_log_value(value) -> str:
    text = str(value)[:200]
    return (
        text.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace(" ", "\\ ")
    )


def emit_incident_im_event(event: str, **fields) -> None:
    """Emit an allowlisted metric event without affecting the business path."""

    safe_event = event if event in _SAFE_EVENTS else "incident_im_unknown"
    safe_fields = {key: value for key, value in fields.items() if key in _SAFE_FIELDS}
    rendered_fields = " ".join(
        f"{key}={_render_log_value(value)}"
        for key, value in sorted(safe_fields.items())
    )
    message = f"incident im observability event={safe_event}"
    if rendered_fields:
        message = f"{message} {rendered_fields}"
    try:
        logger.info(
            message, extra={"event": safe_event, **safe_fields},
        )
    except Exception:
        pass
