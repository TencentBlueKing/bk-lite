from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info
from apps.monitor.services.display_metric_snapshot import DISPLAY_METRICS_INSTANCE_CAP
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.architecture_node_status import MAX_INST_UUIDS, _normalize_inst_uuids
from apps.operation_analysis.services.monitor_batches import chunks
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.cmdb import CMDB
from apps.rpc.monitor import Monitor

_CMDB_CHUNK = NETWORK_STATUS_TOPOLOGY_MAX_NODES


class ArchitectureDisplayMetricsService:
    @classmethod
    def query(cls, request, inst_uuids: list) -> dict:
        unique, _rejected = _normalize_inst_uuids(inst_uuids)
        if len(unique) > MAX_INST_UUIDS:
            raise ValidationError(
                {
                    "inst_uuids": oa_message(
                        "messages.architecture_node_status_limit",
                        "inst_uuids 去重后不能超过 500",
                    )
                }
            )
        if not unique:
            return {"objects": {}, "items": []}
        user_info = build_nats_user_info(request)
        monitor_to_uuids: dict[str, list[str]] = {}
        for batch_index, chunk in enumerate(chunks(unique, _CMDB_CHUNK)):
            outcome = cls._fetch_monitor_chunk(chunk, user_info, batch_index)
            if outcome is None:
                continue
            for inst_uuid in chunk:
                item = outcome.get(inst_uuid)
                monitor_id = _monitor_id(item)
                if not monitor_id:
                    continue
                bucket = monitor_to_uuids.setdefault(monitor_id, [])
                if inst_uuid not in bucket:
                    bucket.append(inst_uuid)

        objects: dict[str, dict] = {}
        values_by_monitor: dict[str, tuple[str, dict]] = {}
        monitor_ids = list(monitor_to_uuids)
        for batch_index, chunk in enumerate(chunks(monitor_ids, DISPLAY_METRICS_INSTANCE_CAP)):
            payload = cls._fetch_metrics_chunk(chunk, user_info, batch_index)
            if payload is None:
                continue
            for object_id, entry in payload["objects"].items():
                objects[object_id] = entry
            for item in payload["items"]:
                requested_id = item.get("requested_id")
                if requested_id in (None, ""):
                    continue
                values_by_monitor[str(requested_id)] = (
                    str(item.get("monitor_object_id") or ""),
                    item.get("values") if isinstance(item.get("values"), dict) else {},
                )

        items = []
        for monitor_id, uuids in monitor_to_uuids.items():
            found = values_by_monitor.get(monitor_id)
            if found is None:
                continue
            monitor_object_id, values = found
            if not monitor_object_id:
                continue
            for inst_uuid in uuids:
                items.append(
                    {
                        "inst_uuid": inst_uuid,
                        "monitor_object_id": monitor_object_id,
                        "values": values,
                    }
                )
        return {"objects": objects, "items": items}

    @classmethod
    def _fetch_monitor_chunk(cls, chunk: list[str], user_info: dict, batch_index: int):
        try:
            result = CMDB().get_monitor_ids_by_inst_uuids(inst_uuids=chunk, user_info=user_info)
        except Exception as exc:
            cls._log_batch_failure("monitor_ids", batch_index, len(chunk), exc)
            return None
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._log_batch_failure("monitor_ids", batch_index, len(chunk), None)
            return None
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        items = {}
        forbidden = {str(value) for value in data.get("forbidden_inst_uuids") or [] if value not in (None, "")}
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            inst_uuid = item.get("inst_uuid")
            if inst_uuid in (None, "") or str(inst_uuid) in forbidden:
                continue
            items[str(inst_uuid)] = item
        return items

    @classmethod
    def _fetch_metrics_chunk(cls, chunk: list[str], user_info: dict, batch_index: int):
        try:
            result = Monitor().query_instance_display_metrics(instance_ids=chunk, user_info=user_info)
        except Exception as exc:
            cls._log_batch_failure("display_metrics", batch_index, len(chunk), exc)
            return None
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._log_batch_failure("display_metrics", batch_index, len(chunk), None)
            return None
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        objects = {}
        for object_id, entry in (data.get("objects") or {}).items():
            if not isinstance(entry, dict):
                continue
            columns = []
            for column in entry.get("columns") or []:
                if not isinstance(column, dict):
                    continue
                keys = [key for key in column.get("keys") or [] if isinstance(key, str) and key]
                if not keys:
                    continue
                name = column.get("name") if isinstance(column.get("name"), str) else ""
                columns.append({"name": name, "keys": keys})
            objects[str(object_id)] = {"columns": columns}
        items = []
        for item in data.get("items") or []:
            if isinstance(item, dict):
                items.append(item)
        return {"objects": objects, "items": items}

    @staticmethod
    def _log_batch_failure(failed_stage: str, batch_index: int, batch_size: int, exc: BaseException | None) -> None:
        error_type = type(exc).__name__ if exc is not None else "NatsResultFalse"
        logger.error(
            "event=architecture_display_metrics_batch_failed failed_stage=%s error_type=%s batch_index=%s batch_size=%s",
            failed_stage,
            error_type,
            batch_index,
            batch_size,
            exc_info=safe_exception_info(exc) if exc is not None else None,
        )


def _monitor_id(item) -> str:
    if not isinstance(item, dict):
        return ""
    monitor_id = item.get("monitor_id")
    if monitor_id in (None, ""):
        return ""
    return str(monitor_id).strip()
