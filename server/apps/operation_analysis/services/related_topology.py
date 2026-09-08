from typing import Any

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.rpc.cmdb import CMDB
from apps.rpc.monitor import Monitor

_NATS_TO_HTTP_CODE = {
    "invalid_inst_uuid": "invalid_request",
    "not_found": "not_found",
    "permission_denied": "permission_denied",
}

_NATS_MESSAGES = {
    "invalid_request": "inst_uuid 不合法",
    "not_found": "实例不存在",
    "permission_denied": "无权限查看该实例",
    "source_failure": "关联拓扑查询失败",
}


class RelatedTopologyError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or _NATS_MESSAGES.get(code, _NATS_MESSAGES["source_failure"])
        super().__init__(self.message)


class RelatedTopologyService:
    @classmethod
    def build(cls, request, inst_uuid: str) -> dict[str, Any]:
        user_info = build_nats_user_info(request)
        tree = cls._fetch_neighbors(inst_uuid, user_info)
        mappings = cls._fetch_monitor_ids(cls._collect_uuids(tree), user_info, inst_uuid)
        summaries = cls._fetch_alert_summaries(mappings, user_info, inst_uuid)
        mapping_by_uuid = {item["inst_uuid"]: item for item in mappings if item.get("inst_uuid")}
        summary_by_monitor = {item["instance_id"]: item for item in summaries if item.get("instance_id")}
        return {
            "center_inst_uuid": inst_uuid,
            "src_result": cls._overlay_node(tree.get("src_result"), mapping_by_uuid, summary_by_monitor),
            "dst_result": cls._overlay_node(tree.get("dst_result"), mapping_by_uuid, summary_by_monitor),
        }

    @classmethod
    def _fetch_neighbors(cls, inst_uuid: str, user_info: dict) -> dict[str, Any]:
        try:
            result = CMDB().topo_search_lite_by_uuid(inst_uuid=inst_uuid, user_info=user_info)
        except Exception as exc:
            cls._log_source_failure("neighbors", inst_uuid, exc)
            raise RelatedTopologyError("source_failure") from exc
        return cls._unwrap_cmdb_tree(result, inst_uuid)

    @classmethod
    def _fetch_monitor_ids(cls, inst_uuids: list[str], user_info: dict, inst_uuid: str) -> list[dict]:
        if not inst_uuids:
            return []
        try:
            result = CMDB().get_monitor_ids_by_inst_uuids(inst_uuids=inst_uuids, user_info=user_info)
        except Exception as exc:
            cls._log_source_failure("monitor_ids", inst_uuid, exc)
            raise RelatedTopologyError("source_failure") from exc
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._raise_nats_false_result("monitor_ids", inst_uuid)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        items = data.get("items") or []
        return [item for item in items if isinstance(item, dict)]

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
        if not monitor_ids:
            return []
        try:
            result = Monitor().ingest_client.run(
                "query_latest_active_alerts",
                query_data={"instance_ids": monitor_ids, "limit": 1},
                user_info=user_info,
            )
        except Exception as exc:
            cls._log_source_failure("active_alerts", inst_uuid, exc)
            raise RelatedTopologyError("source_failure") from exc
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._raise_nats_false_result("active_alerts", inst_uuid)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        summaries = data.get("instance_summaries") or []
        return [item for item in summaries if isinstance(item, dict)]

    @classmethod
    def _unwrap_cmdb_tree(cls, result: Any, inst_uuid: str) -> dict[str, Any]:
        if not isinstance(result, dict) or result.get("result") is not True:
            code = "source_failure"
            data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}
            nats_code = data.get("code")
            if nats_code in _NATS_TO_HTTP_CODE:
                code = _NATS_TO_HTTP_CODE[nats_code]
            if code == "source_failure":
                cls._raise_nats_false_result("neighbors", inst_uuid)
            raise RelatedTopologyError(code)
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    @classmethod
    def _collect_uuids(cls, node: Any) -> list[str]:
        collected: list[str] = []
        seen: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                inst_uuid = value.get("inst_uuid")
                if inst_uuid not in (None, ""):
                    text = str(inst_uuid)
                    if text not in seen:
                        seen.add(text)
                        collected.append(text)
                for child in value.get("children") or []:
                    walk(child)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item)

        if isinstance(node, dict) and ("src_result" in node or "dst_result" in node):
            walk(node.get("src_result"))
            walk(node.get("dst_result"))
        else:
            walk(node)
        return collected

    @classmethod
    def _overlay_node(cls, node: Any, mapping_by_uuid: dict, summary_by_monitor: dict) -> dict:
        if not isinstance(node, dict) or not node.get("inst_uuid"):
            return {}
        inst_uuid = str(node["inst_uuid"])
        mapping = mapping_by_uuid.get(inst_uuid) or {}
        monitor_id = mapping.get("monitor_id")
        monitor_id = "" if monitor_id in (None, "") else str(monitor_id)
        overlaid = {key: value for key, value in node.items() if key != "children"}
        overlaid["inst_uuid"] = inst_uuid
        overlaid["monitor_id"] = monitor_id
        if not monitor_id:
            overlaid["alert_count"] = None
            overlaid["max_level"] = None
        else:
            summary = summary_by_monitor.get(monitor_id) or {}
            count = summary.get("count")
            overlaid["alert_count"] = int(count) if count not in (None, "") else 0
            max_level = summary.get("max_level")
            overlaid["max_level"] = str(max_level) if max_level not in (None, "") else None
        overlaid["children"] = [
            child for item in node.get("children") or [] if (child := cls._overlay_node(item, mapping_by_uuid, summary_by_monitor))
        ]
        return overlaid

    @classmethod
    def _raise_nats_false_result(cls, failed_stage: str, inst_uuid: str) -> None:
        logger.error(
            "event=related_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s",
            failed_stage,
            "NatsResultFalse",
            inst_uuid,
        )
        raise RelatedTopologyError("source_failure")

    @staticmethod
    def _log_source_failure(failed_stage: str, inst_uuid: str, exc: BaseException) -> None:
        logger.exception(
            "event=related_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s",
            failed_stage,
            type(exc).__name__,
            inst_uuid,
        )
