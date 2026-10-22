from typing import Any

from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.cmdb.services.instance_identity import optional_inst_uuid
from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.monitor_batches import chunks
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.cmdb import CMDB
from apps.rpc.monitor import Monitor

MAX_INST_UUIDS = 500
_CHUNK_SIZE = NETWORK_STATUS_TOPOLOGY_MAX_NODES
_SEVERE_LEVELS = ["critical", "error"]
_ZERO_LEVEL_COUNTS = {"critical": 0, "error": 0, "warning": 0}


class ArchitectureNodeStatusService:
    @classmethod
    def query(cls, request, inst_uuids: list) -> dict[str, list[dict]]:
        unique, rejected = _normalize_inst_uuids(inst_uuids)
        if len(unique) > MAX_INST_UUIDS:
            raise ValidationError(
                {
                    "inst_uuids": oa_message(
                        "messages.architecture_node_status_limit",
                        "inst_uuids 去重后不能超过 500",
                    )
                }
            )
        user_info = build_nats_user_info(request)
        resolved = cls._resolve(unique, user_info)
        items = [_empty_item(uuid, "invalid") for uuid in rejected]
        items.extend(resolved)
        return {"items": items}

    @classmethod
    def _resolve(cls, inst_uuids: list[str], user_info: dict) -> list[dict]:
        if not inst_uuids:
            return []
        mappings: dict[str, dict] = {}
        states: dict[str, str] = {}
        for batch_index, chunk in enumerate(chunks(inst_uuids, _CHUNK_SIZE)):
            outcome = cls._fetch_monitor_chunk(chunk, user_info, batch_index)
            if outcome is None:
                for inst_uuid in chunk:
                    states[inst_uuid] = "unknown"
                continue
            chunk_items, forbidden = outcome
            for inst_uuid in chunk:
                item = chunk_items.get(inst_uuid)
                if item is not None:
                    mappings[inst_uuid] = item
                    states[inst_uuid] = "mapped"
                elif inst_uuid in forbidden:
                    states[inst_uuid] = "forbidden"
                else:
                    states[inst_uuid] = "invalid"

        monitor_ids = []
        seen_monitors = set()
        for inst_uuid, item in mappings.items():
            if states.get(inst_uuid) != "mapped":
                continue
            monitor_id = _monitor_id(item)
            if not monitor_id or monitor_id in seen_monitors:
                continue
            seen_monitors.add(monitor_id)
            monitor_ids.append(monitor_id)

        summaries, failed_monitors = cls._fetch_alert_summaries(monitor_ids, user_info)
        items = []
        for inst_uuid in inst_uuids:
            state = states.get(inst_uuid)
            if state == "mapped":
                items.append(_status_from_mapping(mappings[inst_uuid], summaries, failed_monitors))
            elif state in {"forbidden", "invalid", "unknown"}:
                items.append(_empty_item(inst_uuid, state))
            else:
                items.append(_empty_item(inst_uuid, "unknown"))
        return items

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
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            inst_uuid = item.get("inst_uuid")
            if inst_uuid in (None, ""):
                continue
            items[str(inst_uuid)] = item
        forbidden = set()
        for inst_uuid in data.get("forbidden_inst_uuids") or []:
            if inst_uuid in (None, ""):
                continue
            forbidden.add(str(inst_uuid))
        return items, forbidden

    @classmethod
    def _fetch_alert_summaries(cls, monitor_ids: list[str], user_info: dict):
        """Two existing summary queries. A counts every active alert. B counts critical and error only.

        Severe is B. Warning is the rest, floored at 0 when the two snapshots diverge.
        Either call failing marks the whole batch unknown and does not read the other snapshot.
        """
        counts: dict[str, tuple[int | None, int | None]] = {}
        failed: set[str] = set()
        for batch_index, chunk in enumerate(chunks(monitor_ids, _CHUNK_SIZE)):
            active = cls._query_alert_counts(chunk, user_info, batch_index, None)
            if active is None:
                failed.update(chunk)
                continue
            severe = cls._query_alert_counts(chunk, user_info, batch_index, _SEVERE_LEVELS)
            if severe is None:
                failed.update(chunk)
                continue
            for monitor_id in chunk:
                counts[monitor_id] = (active.get(monitor_id), severe.get(monitor_id))
        return counts, failed

    @classmethod
    def _query_alert_counts(
        cls,
        chunk: list[str],
        user_info: dict,
        batch_index: int,
        level: list[str] | None,
    ) -> dict[str, int | None] | None:
        query_data: dict[str, Any] = {"instance_ids": chunk, "limit": 1}
        if level is not None:
            query_data["level"] = level
        try:
            result = Monitor().ingest_client.run(
                "query_latest_active_alerts",
                query_data=query_data,
                user_info=user_info,
            )
        except Exception as exc:
            cls._log_batch_failure("active_alerts", batch_index, len(chunk), exc)
            return None
        if not isinstance(result, dict) or result.get("result") is not True:
            cls._log_batch_failure("active_alerts", batch_index, len(chunk), None)
            return None
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        indexed: dict[str, int | None] = {}
        for item in data.get("instance_summaries") or []:
            if not isinstance(item, dict):
                continue
            instance_id = item.get("instance_id")
            if instance_id in (None, ""):
                continue
            indexed[str(instance_id)] = _coerce_alert_count(item.get("count"))
        return indexed

    @staticmethod
    def _log_batch_failure(failed_stage: str, batch_index: int, batch_size: int, exc: BaseException | None) -> None:
        error_type = type(exc).__name__ if exc is not None else "NatsResultFalse"
        logger.error(
            "event=architecture_node_status_batch_failed failed_stage=%s error_type=%s batch_index=%s batch_size=%s",
            failed_stage,
            error_type,
            batch_index,
            batch_size,
            exc_info=safe_exception_info(exc) if exc is not None else None,
        )


def _normalize_inst_uuids(raw: list) -> tuple[list[str], list[str]]:
    if not isinstance(raw, list):
        raise ValidationError(
            {
                "inst_uuids": oa_message(
                    "messages.architecture_node_status_type",
                    "inst_uuids 必须是列表",
                )
            }
        )
    unique: list[str] = []
    rejected: list[str] = []
    seen = set()
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                {
                    "inst_uuids": oa_message(
                        "messages.architecture_node_status_item",
                        "inst_uuids 的每一项必须是非空字符串",
                    )
                }
            )
        normalized = optional_inst_uuid(value)
        if normalized is None:
            if value not in seen:
                seen.add(value)
                rejected.append(value)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique, rejected


def _monitor_id(item: dict) -> str:
    monitor_id = item.get("monitor_id")
    if monitor_id in (None, ""):
        return ""
    return str(monitor_id)


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _empty_level_counts() -> dict[str, int]:
    return dict(_ZERO_LEVEL_COUNTS)


def _empty_item(inst_uuid: str, status: str) -> dict:
    return {
        "inst_uuid": inst_uuid,
        "status": status,
        "alert_count": 0,
        "max_level": None,
        "level_counts": _empty_level_counts(),
        "monitor_id": "",
        "model_id": "",
        "inst_name": "",
    }


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


def _status_from_counts(base: dict, active_count: int, severe_count: int) -> dict:
    severe = severe_count
    warning = max(active_count - severe_count, 0)
    if severe > 0:
        status, max_level = "critical", "critical"
    elif warning > 0:
        status, max_level = "warning", "warning"
    else:
        return {
            **base,
            "status": "normal",
            "alert_count": 0,
            "max_level": None,
            "level_counts": _empty_level_counts(),
        }
    # B lumps critical and error. The severe total lives in critical; error stays 0.
    return {
        **base,
        "status": status,
        "alert_count": severe + warning,
        "max_level": max_level,
        "level_counts": {"critical": severe, "error": 0, "warning": warning},
    }


def _status_from_mapping(
    item: dict,
    counts: dict[str, tuple[int | None, int | None]],
    failed_monitors: set[str],
) -> dict:
    inst_uuid = str(item.get("inst_uuid"))
    monitor_id = _monitor_id(item)
    base = {
        "inst_uuid": inst_uuid,
        "monitor_id": monitor_id,
        "model_id": _text(item.get("model_id")),
        "inst_name": _text(item.get("inst_name")),
        "alert_count": 0,
        "max_level": None,
        "level_counts": _empty_level_counts(),
    }
    if not monitor_id:
        return {**base, "status": "unmonitored"}
    if monitor_id in failed_monitors:
        return {**base, "status": "unknown"}
    pair = counts.get(monitor_id)
    if pair is None:
        return {**base, "status": "unknown"}
    active_count, severe_count = pair
    if active_count is None or severe_count is None:
        return {**base, "status": "unknown"}
    return _status_from_counts(base, active_count, severe_count)
