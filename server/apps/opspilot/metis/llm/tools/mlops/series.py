"""从监控查询结果里拆出一条条序列。"""

from typing import Any

from apps.opspilot.metis.llm.tools.mlops.reshape import series_identity


def extract_monitor_series(payload: Any) -> list[dict]:
    rows = _result_rows(payload)
    series = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        labels = row.get("metric") if isinstance(row.get("metric"), dict) else {}
        points = []
        for pair in row.get("values") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                points.append({"timestamp": pair[0], "value": pair[1]})
        identity = series_identity(labels)
        instance = str(labels.get("instance") or "")
        declared = str(labels.get("instance_id") or "").strip()
        series.append(
            {
                "instance_id": declared or identity or instance or None,
                "instance": instance,
                "labels": labels,
                "points": points,
            }
        )
    return series


def series_keys(item: dict) -> set[str]:
    labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
    keys = set()
    for value in (
        item.get("instance_id"),
        item.get("instance"),
        labels.get("instance_id"),
        labels.get("instance"),
        series_identity(labels),
    ):
        text = str(value or "").strip()
        if text:
            keys.add(text)
    return keys


def select_series(series: list[dict], instance_ids: list) -> tuple[list[dict], list[str]]:
    wanted = []
    for item in instance_ids or []:
        text = str(item or "").strip()
        if text and text not in wanted:
            wanted.append(text)
    selected = []
    missing = []
    seen = set()
    for wanted_id in wanted:
        hits = [item for item in series if wanted_id in series_keys(item)]
        if not hits:
            missing.append(wanted_id)
            continue
        for hit in hits:
            marker = id(hit)
            if marker in seen:
                continue
            seen.add(marker)
            selected.append(hit)
    return selected, missing


def _result_rows(payload: Any) -> list:
    container = payload
    for _ in range(6):
        if not isinstance(container, dict):
            break
        for key in ("result", "series"):
            rows = container.get(key)
            if isinstance(rows, list):
                return rows
        nested = container.get("data")
        if isinstance(nested, list):
            return nested
        if not isinstance(nested, dict):
            break
        container = nested
    return []
