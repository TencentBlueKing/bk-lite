from __future__ import annotations

from typing import Any

WORKFLOW_TRIGGER_TYPES = frozenset({"FORM", "SCHEDULE", "WEBHOOK", "NATS"})


def workflow_trigger_types(canvas_metadata: Any) -> list[str]:
    """Return the normalized trigger-type projection exposed by workflow lists."""
    if not isinstance(canvas_metadata, dict):
        return []
    trigger_nodes = canvas_metadata.get("trigger_nodes")
    if not isinstance(trigger_nodes, list):
        return []
    return sorted(
        {
            trigger_type
            for item in trigger_nodes
            if isinstance(item, dict) and isinstance((trigger_type := item.get("trigger_type")), str) and trigger_type in WORKFLOW_TRIGGER_TYPES
        }
    )
