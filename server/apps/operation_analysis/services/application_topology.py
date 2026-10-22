from typing import Any

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.monitor_batches import chunks as _chunks
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.cmdb import CMDB
from apps.rpc.monitor import Monitor

_NATS_TO_HTTP_CODE = {
    "invalid_inst_uuid": "invalid_request",
    "invalid_depth": "invalid_request",
    "not_found": "not_found",
    "permission_denied": "permission_denied",
    "unsupported_model": "unsupported_model",
}

_MESSAGES = {
    "invalid_request": ("messages.application_topology_invalid", "应用拓扑参数不合法"),
    "not_found": ("messages.application_topology_not_found", "实例不存在"),
    "permission_denied": ("messages.application_topology_denied", "无权限查看该实例"),
    "unsupported_model": ("messages.application_topology_unsupported", "应用拓扑仅支持应用系统"),
    "source_failure": ("messages.application_topology_query_failed", "应用拓扑查询失败"),
}

_MONITOR_ID_CHUNK = NETWORK_STATUS_TOPOLOGY_MAX_NODES


class ApplicationTopologyError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        key, default = _MESSAGES.get(code, _MESSAGES["source_failure"])
        self.message = message or oa_message(key, default)
        super().__init__(self.message)


class ApplicationTopologyService:
    @classmethod
    def build(cls, request, inst_uuid: str, depth: int) -> dict[str, Any]:
        user_info = build_nats_user_info(request)
        topology = cls._fetch_topology(inst_uuid, depth, user_info)
        nodes = [item for item in topology.get("nodes") or [] if isinstance(item, dict)]
        mappings = cls._fetch_monitor_ids(cls._collect_uuids(nodes), user_info, inst_uuid)
        summaries = cls._fetch_alert_summaries(mappings, user_info, inst_uuid)
        mapping_by_uuid = {item["inst_uuid"]: item for item in mappings if item.get("inst_uuid")}
        summary_by_monitor = {item["instance_id"]: item for item in summaries if item.get("instance_id")}
        center = topology.get("center") if isinstance(topology.get("center"), dict) else {}
        return {
            "center_inst_uuid": inst_uuid,
            "depth": depth,
            "center": cls._overlay_node(center, mapping_by_uuid, summary_by_monitor),
            "nodes": [cls._overlay_node(node, mapping_by_uuid, summary_by_monitor) for node in nodes],
            "links": [item for item in topology.get("links") or [] if isinstance(item, dict)],
        }

    @classmethod
    def _fetch_topology(cls, inst_uuid: str, depth: int, user_info: dict) -> dict[str, Any]:
        result = cls._call_source(
            "topology",
            inst_uuid,
            lambda: CMDB().application_resource_topology_by_uuid(
                inst_uuid=inst_uuid,
                depth=depth,
                user_info=user_info,
            ),
        )
        if not isinstance(result, dict) or result.get("result") is not True:
            data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}
            code = _NATS_TO_HTTP_CODE.get(data.get("code"), "source_failure")
            if code == "source_failure":
                cls._raise_nats_false_result("topology", inst_uuid)
            raise ApplicationTopologyError(code)
        data = result.get("data")
        if not isinstance(data, dict) or not (data.get("center") or {}).get("id"):
            raise ApplicationTopologyError("not_found")
        return data

    @classmethod
    def _fetch_monitor_ids(cls, inst_uuids: list[str], user_info: dict, inst_uuid: str) -> list[dict]:
        items: list[dict] = []
        for chunk in _chunks(inst_uuids, _MONITOR_ID_CHUNK):
            result = cls._call_overlay(
                "monitor_ids",
                inst_uuid,
                lambda: CMDB().get_monitor_ids_by_inst_uuids(inst_uuids=chunk, user_info=user_info),
            )
            if result is None:
                continue
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            items.extend(item for item in data.get("items") or [] if isinstance(item, dict))
        return items

    @classmethod
    def _fetch_alert_summaries(cls, mappings: list[dict], user_info: dict, inst_uuid: str) -> list[dict]:
        monitor_ids = []
        seen = set()
        for item in mappings:
            monitor_id = item.get("monitor_id")
            if monitor_id in (None, ""):
                continue
            monitor_id = str(monitor_id)
            if monitor_id in seen:
                continue
            seen.add(monitor_id)
            monitor_ids.append(monitor_id)
        summaries: list[dict] = []
        for chunk in _chunks(monitor_ids, _MONITOR_ID_CHUNK):
            result = cls._call_overlay(
                "active_alerts",
                inst_uuid,
                lambda: Monitor().ingest_client.run(
                    "query_latest_active_alerts",
                    query_data={"instance_ids": chunk, "limit": 1},
                    user_info=user_info,
                ),
            )
            if result is None:
                continue
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            summaries.extend(item for item in data.get("instance_summaries") or [] if isinstance(item, dict))
        return summaries

    @staticmethod
    def _collect_uuids(nodes: list[dict]) -> list[str]:
        collected = []
        seen = set()
        for node in nodes:
            inst_uuid = node.get("id")
            if inst_uuid in (None, ""):
                continue
            text = str(inst_uuid)
            if text in seen:
                continue
            seen.add(text)
            collected.append(text)
        return collected

    @staticmethod
    def _overlay_node(node: dict, mapping_by_uuid: dict, summary_by_monitor: dict) -> dict:
        if not isinstance(node, dict) or not node.get("id"):
            return {}
        inst_uuid = str(node["id"])
        mapping = mapping_by_uuid.get(inst_uuid) or {}
        monitor_id = mapping.get("monitor_id")
        monitor_id = "" if monitor_id in (None, "") else str(monitor_id)
        overlaid = dict(node)
        overlaid["id"] = inst_uuid
        overlaid["monitor_id"] = monitor_id
        if not monitor_id or monitor_id not in summary_by_monitor:
            overlaid["alert_count"] = None
            overlaid["max_level"] = None
            return overlaid
        summary = summary_by_monitor[monitor_id]
        count = _coerce_alert_count(summary.get("count"))
        if count is None:
            overlaid["alert_count"] = None
            overlaid["max_level"] = None
            return overlaid
        overlaid["alert_count"] = count
        max_level = summary.get("max_level")
        overlaid["max_level"] = str(max_level) if max_level not in (None, "") else None
        return overlaid

    @classmethod
    def _call_source(cls, failed_stage: str, inst_uuid: str, call):
        try:
            return call()
        except Exception as exc:
            cls._log_source_failure(failed_stage, inst_uuid, exc)
            raise ApplicationTopologyError("source_failure") from exc

    @classmethod
    def _call_overlay(cls, failed_stage: str, inst_uuid: str, call):
        """拓扑之后的监控映射和活跃告警失败只记日志，不挡住已经取到的图。"""
        try:
            result = call()
        except Exception as exc:
            cls._log_source_failure(failed_stage, inst_uuid, exc)
            return None
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._log_nats_false_result(failed_stage, inst_uuid)
            return None
        return result

    @classmethod
    def _log_nats_false_result(cls, failed_stage: str, inst_uuid: str) -> None:
        logger.error(
            "event=application_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s",
            failed_stage,
            "NatsResultFalse",
            inst_uuid,
        )

    @classmethod
    def _raise_nats_false_result(cls, failed_stage: str, inst_uuid: str) -> None:
        cls._log_nats_false_result(failed_stage, inst_uuid)
        raise ApplicationTopologyError("source_failure")

    @staticmethod
    def _log_source_failure(failed_stage: str, inst_uuid: str, exc: BaseException) -> None:
        logger.error(
            "event=application_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s",
            failed_stage,
            type(exc).__name__,
            inst_uuid,
            exc_info=safe_exception_info(exc),
        )


def _coerce_alert_count(count: Any) -> int | None:
    if isinstance(count, bool) or count in (None, ""):
        return None
    try:
        value = int(count)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value
