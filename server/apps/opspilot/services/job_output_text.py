"""把脚本展示块从将要送给模型的正文里拿掉。"""

import json

_HIDDEN_JOB_EVENTS = {"job_script_output", "job_record"}


def model_visible_text(content: str) -> str:
    """作业记录和脚本展示只留作业号和终态。没有这些块时原样返回。"""

    if not content or not any(name in content for name in _HIDDEN_JOB_EVENTS):
        return content
    stripped = content.strip()
    if not stripped.startswith("["):
        return ""
    try:
        events = json.loads(stripped)
    except json.JSONDecodeError:
        return ""
    if not isinstance(events, list):
        return ""
    parts = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "TEXT_MESSAGE_CONTENT":
            continue
        if event.get("name") in _HIDDEN_JOB_EVENTS:
            continue
        delta = str(event.get("delta") or "")
        if any(name in delta for name in _HIDDEN_JOB_EVENTS):
            continue
        if delta:
            parts.append(delta)
    return "".join(parts).strip()
