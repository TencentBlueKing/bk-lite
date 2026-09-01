from collections.abc import Iterable

from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info

_COLUMN_KEYS = ("column_id", "column_name", "column_type", "order", "is_row_key")


def build_attribute_snapshot(attributes: list[dict], attr_ids: Iterable[str]) -> dict:
    """生成最小、稳定的变更记录字段定义快照。"""
    touched = set(attr_ids)
    snapshots: dict[str, dict] = {}
    for attribute in attributes:
        attr_id = attribute.get("attr_id")
        if not attr_id or attr_id not in touched:
            continue
        item = {
            "attr_id": attr_id,
            "attr_name": attribute.get("attr_name") or attr_id,
            "attr_type": attribute.get("attr_type") or "",
        }
        if item["attr_type"] == "table":
            columns = attribute.get("option") if isinstance(attribute.get("option"), list) else []
            item["columns"] = [
                {key: column[key] for key in _COLUMN_KEYS if key in column}
                for column in columns
                if isinstance(column, dict) and column.get("column_id")
            ]
        snapshots[attr_id] = item
    return {"version": 1, "attributes": snapshots}


def load_attribute_snapshot(model_id: str, attr_ids: Iterable[str]) -> dict:
    """从当前模型定义构建快照；失败不阻断实例写入。"""
    from apps.cmdb.services.model import ModelManage

    try:
        return build_attribute_snapshot(ModelManage.search_model_attr(model_id), attr_ids)
    except Exception as exc:
        logger.error(
            "event=cmdb_change_record_snapshot_failed model_id=%s failed_stage=%s error_type=%s",
            model_id,
            "load_attributes",
            exc.__class__.__name__,
            exc_info=safe_exception_info(exc),
        )
        return {}
