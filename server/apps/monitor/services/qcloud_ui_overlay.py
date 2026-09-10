"""腾讯云监控 UI：从磁盘 UI.json 热同步地域等字段。

已部署环境的 DB 模板可能仍缺 region；通过接口读模板时补齐，避免必须重跑 plugin_init。
"""

from __future__ import annotations

from copy import deepcopy

_QCLOUD_FILE_OVERLAY_FIELD_KEYS = (
    "label",
    "label_en",
    "type",
    "required",
    "editable",
    "default_value",
    "description",
    "description_en",
    "options",
    "options_key",
    "widget_props",
    "transform_on_edit",
)


def is_qcloud_ui_template(file_ui: dict | None, content: dict | None = None) -> bool:
    """判断是否为腾讯云监控插件 UI（磁盘或 DB 模板）。"""
    for candidate in (file_ui, content):
        if not isinstance(candidate, dict):
            continue
        if candidate.get("instance_type") == "qcloud":
            return True
        config_type = candidate.get("config_type") or []
        if isinstance(config_type, str):
            config_type = [config_type]
        if "qcloud" in config_type:
            return True
    return False


def merge_qcloud_ui_from_file(enriched: dict | None, file_ui: dict | None) -> dict | None:
    """从磁盘 UI.json 热同步腾讯云地域等字段。"""
    if not isinstance(enriched, dict) or not isinstance(file_ui, dict):
        return enriched
    if not is_qcloud_ui_template(file_ui, enriched):
        return enriched

    instance_id = file_ui.get("instance_id")
    if isinstance(instance_id, str) and instance_id.strip():
        enriched["instance_id"] = instance_id

    file_fields = [field for field in (file_ui.get("form_fields") or []) if isinstance(field, dict) and field.get("name")]
    if not file_fields:
        return enriched

    form_fields = enriched.get("form_fields")
    if not isinstance(form_fields, list):
        enriched["form_fields"] = deepcopy(file_fields)
        return enriched

    existing_by_name = {str(field.get("name")): field for field in form_fields if isinstance(field, dict) and field.get("name")}
    for source in file_fields:
        name = str(source.get("name"))
        target = existing_by_name.get(name)
        if target is None:
            form_fields.append(deepcopy(source))
            existing_by_name[name] = form_fields[-1]
            continue
        for key in _QCLOUD_FILE_OVERLAY_FIELD_KEYS:
            if key not in source:
                continue
            value = source.get(key)
            if value in (None, ""):
                continue
            target[key] = deepcopy(value)
    return enriched
