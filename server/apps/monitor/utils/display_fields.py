import hashlib
import json

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.utils.alert_name_variables import (
    normalize_variable_id,
    validate_variable_id,
)

DISPLAY_FIELD_TYPES = {"metric", "field"}

# 展示列语义角色。云平台子对象的 IP 来自指标 label，与基础对象的 asset.ip 摘要列是两套机制；
# 打上 role 后页面按内置 IP 列渲染，各平台上报的 label 名（resource_ip / ip）无需统一。
DISPLAY_FIELD_ROLES = {"resource_ip"}


def build_display_column_key(display_field):
    """用字段类型和有序绑定生成不受标题、语言及默认顺序影响的列标识。"""
    column_type = display_field.get("type") or "metric"
    identity = {
        "type": column_type,
        "metrics": [
            {
                "plugin": binding.get("plugin") or "",
                "metric": binding.get("metric") or "",
                **(
                    {"field": binding.get("field") or ""}
                    if column_type == "field"
                    else {}
                ),
            }
            for binding in display_field.get("metrics") or []
        ],
    }
    raw = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{column_type}:{digest}"


def validate_display_fields(monitor_object, display_fields):
    """校验 display_fields 结构与指标存在性，返回规整后的列表。"""
    if not isinstance(display_fields, list):
        raise BaseAppException("display_fields must be a list")

    existing = {
        (m["monitor_plugin__name"], m["name"])
        for m in Metric.objects.filter(monitor_object=monitor_object).values("monitor_plugin__name", "name")
    }

    normalized = []
    used_variable_ids: set[str] = set()
    used_roles: set[str] = set()
    for idx, col in enumerate(display_fields):
        if not isinstance(col, dict):
            raise BaseAppException("each display field must be an object")
        name = (col.get("name") or "").strip()
        if not name:
            raise BaseAppException("display field name is required")
        col_type = (col.get("type") or "metric").strip()
        if col_type not in DISPLAY_FIELD_TYPES:
            raise BaseAppException(f"display field '{name}' has unsupported type: {col_type}")
        metrics = col.get("metrics") or []
        if not isinstance(metrics, list) or not metrics:
            raise BaseAppException(f"display field '{name}' requires at least one metric")
        norm_metrics = []
        for binding in metrics:
            if not isinstance(binding, dict):
                raise BaseAppException(f"display field '{name}' has a non-object metric binding")
            plugin = (binding.get("plugin") or "").strip()
            metric = (binding.get("metric") or "").strip()
            if not plugin or not metric:
                raise BaseAppException(f"display field '{name}' has an incomplete metric binding")
            if (plugin, metric) not in existing:
                raise BaseAppException(f"metric not found: {plugin}/{metric}")
            norm_binding = {"plugin": plugin, "metric": metric}
            if col_type == "field":
                field = (binding.get("field") or "").strip()
                if not field:
                    raise BaseAppException(f"display field '{name}' has an incomplete field binding")
                norm_binding["field"] = field
            norm_metrics.append(norm_binding)
        variable_id = normalize_variable_id(col.get("variable_id"))
        validate_variable_id(variable_id, used_variable_ids, name)
        role = (col.get("role") or "").strip()
        if role:
            if role not in DISPLAY_FIELD_ROLES:
                raise BaseAppException(f"display field '{name}' uses unsupported role: {role}")
            if col_type != "field":
                raise BaseAppException(f"display field '{name}' role requires field type: {role}")
            if role in used_roles:
                raise BaseAppException(f"display field role '{role}' is duplicated")
            used_roles.add(role)
        norm_col = {"name": name, "sort_order": col.get("sort_order", idx), "metrics": norm_metrics}
        if col_type == "field":
            norm_col["type"] = "field"
        if role:
            norm_col["role"] = role
        if variable_id:
            norm_col["variable_id"] = variable_id
        normalized.append(norm_col)

    sorted_cols = sorted(normalized, key=lambda c: c["sort_order"])
    return [{**col, "sort_order": i} for i, col in enumerate(sorted_cols)]
