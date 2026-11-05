"""Process/application health for ops-analysis tables.

正常 = 近实时有 procstat_cpu_usage 上报，且该进程实例没有 status=new 的告警。
异常 = 有上报且有未关闭告警。无数据 = 所选进程未上报。
告警只看进程实例 ID，不把所属主机的告警算进进程健康。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from apps.monitor.services.host_resource_top import DEFAULT_INTERVAL_SECONDS
from apps.monitor.utils.dimension import parse_instance_id

PROCESS_OBJECT_NAME = "Process"
PROCESS_REPORTING_QUERY = 'procstat_cpu_usage{instance_type="process"}'
STATUS_HEALTHY = "正常"
STATUS_UNHEALTHY = "异常"
STATUS_NO_DATA = "无数据"


def empty_process_health_snapshot() -> list[dict[str, Any]]:
    return []


def _unique_ids(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def process_id_aliases(storage_id: str) -> set[str]:
    """进程告警/上报只认进程存储键，不含主机 logical id。"""
    token = str(storage_id or "").strip()
    if not token:
        return set()
    aliases = {token}
    parsed = parse_instance_id(token)
    if len(parsed) >= 2:
        aliases.add(str(parsed))
        aliases.add(str((str(parsed[0]), str(parsed[1]))))
    return {item for item in aliases if item}


def process_alert_query_ids(instances: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    query_ids: list[str] = []
    for instance in instances:
        storage = str(getattr(instance, "id", "") or "")
        for token in process_id_aliases(storage):
            if token in seen:
                continue
            seen.add(token)
            query_ids.append(token)
    return query_ids


def storage_id_from_process_labels(labels: dict[str, Any] | None) -> str:
    payload = labels or {}
    host = str(payload.get("instance_id") or "").strip()
    process_name = str(payload.get("process_name") or "").strip()
    if not host or not process_name:
        return ""
    return str((host, process_name))


def _interval_seconds(value: Any) -> int:
    try:
        interval = int(value or DEFAULT_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL_SECONDS
    return interval if interval > 0 else DEFAULT_INTERVAL_SECONDS


def process_row_identity(instance: Any) -> dict[str, str]:
    storage = str(getattr(instance, "id", "") or "")
    parsed = parse_instance_id(storage) if storage else ()
    process_name = str(parsed[1]) if len(parsed) > 1 else ""
    host_id = str(parsed[0]) if parsed else ""
    name = str(getattr(instance, "name", "") or "").strip()
    ip = str(getattr(instance, "ip", "") or "").strip()
    host_name = name
    if process_name and name.startswith(f"{process_name}-"):
        host_name = name[len(process_name) + 1 :]
    return {
        "app_name": name or process_name or storage,
        "process_name": process_name or name,
        "host_name": host_name,
        "host_id": host_id,
        "ip": ip,
        "instance_id": storage,
    }


def build_process_health_rows(
    *,
    instances: Iterable[Any],
    reporting_ids: Iterable[str],
    alerting_ids: Iterable[str],
) -> list[dict[str, Any]]:
    reporting = set(_unique_ids(reporting_ids))
    alerting = set(_unique_ids(alerting_ids))
    rows: list[dict[str, Any]] = []
    for instance in instances:
        identity = process_row_identity(instance)
        storage = identity["instance_id"]
        if not storage:
            continue
        aliases = process_id_aliases(storage)
        if not (aliases & reporting):
            status = STATUS_NO_DATA
        elif aliases & alerting:
            status = STATUS_UNHEALTHY
        else:
            status = STATUS_HEALTHY
        rows.append({**identity, "status": status})
    rows.sort(key=lambda item: (item["app_name"], item["process_name"], item["instance_id"]))
    return rows


def reporting_process_ids(
    series: Iterable[Any],
    *,
    selected_ids: Iterable[str],
    interval_by_id: dict[str, int],
    now: datetime | None = None,
) -> set[str]:
    selected = set(_unique_ids(selected_ids))
    if not selected:
        return set()
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    found: set[str] = set()
    for item in series:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric") or {}
        storage = storage_id_from_process_labels(labels if isinstance(labels, dict) else {})
        if not storage:
            continue
        aliases = process_id_aliases(storage)
        matched = aliases & selected
        if not matched:
            continue
        value = item.get("value")
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            continue
        try:
            sampled_at = datetime.fromtimestamp(float(value[0]), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        interval = max((_interval_seconds(interval_by_id.get(token)) for token in matched), default=DEFAULT_INTERVAL_SECONDS)
        if reference_now - sampled_at > timedelta(seconds=2 * interval):
            continue
        found.update(matched)
        found.add(storage)
    return found


class ProcessHealthSnapshotService:
    def __init__(self, *, vm_api, now: datetime | None = None):
        self.vm_api = vm_api
        self.now = now

    def run(self, instances: list[Any], alerting_ids: Iterable[str]) -> list[dict[str, Any]]:
        counted = [item for item in instances if getattr(item, "id", None)]
        if not counted:
            return empty_process_health_snapshot()
        selected_ids = [str(item.id) for item in counted]
        interval_by_id = {str(item.id): _interval_seconds(getattr(item, "interval", None)) for item in counted}
        lookback = max(2 * value for value in interval_by_id.values())
        now = self.now or datetime.now(timezone.utc)
        series = self._query(lookback)
        reporting = reporting_process_ids(
            series,
            selected_ids=selected_ids,
            interval_by_id=interval_by_id,
            now=now,
        )
        return build_process_health_rows(
            instances=counted,
            reporting_ids=reporting,
            alerting_ids=alerting_ids,
        )

    def _query(self, lookback_seconds: int) -> list[Any]:
        try:
            response = self.vm_api.query(PROCESS_REPORTING_QUERY, lookback_delta=f"{lookback_seconds}s")
        except TypeError:
            response = self.vm_api.query(PROCESS_REPORTING_QUERY)
        if not isinstance(response, dict) or response.get("status") != "success":
            message = response.get("error") if isinstance(response, dict) else None
            raise RuntimeError(message or "进程健康指标查询失败")
        result = response.get("data", {}).get("result", [])
        return result if isinstance(result, list) else []
