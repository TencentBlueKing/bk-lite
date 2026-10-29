from __future__ import annotations

import re
from typing import Iterable, Mapping


def linux_process_matches(pattern: str, command_line: str) -> bool:
    text = str(command_line or "")
    expr = str(pattern or "").strip()
    if not expr or not text:
        return False
    try:
        return re.search(expr, text) is not None
    except re.error:
        return False


def match_process_fingerprints(
    command_lines: Iterable[str],
    fingerprints: Iterable[Mapping[str, str]],
) -> list[dict]:
    lines = [str(line or "") for line in command_lines if str(line or "").strip()]
    hits = []
    seen = set()
    for fingerprint in fingerprints or []:
        target_type = str(fingerprint.get("target_type") or "").strip()
        pattern = str(fingerprint.get("linux_process") or "").strip()
        if not target_type or not pattern:
            continue
        if any(linux_process_matches(pattern, line) for line in lines):
            key = (target_type, pattern)
            if key in seen:
                continue
            seen.add(key)
            hits.append({"target_type": target_type, "linux_process": pattern})
    return hits
