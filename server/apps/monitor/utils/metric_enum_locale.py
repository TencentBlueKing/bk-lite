"""Metric Enum unit 按账号语言本地化。

metrics.json / DB 中 Enum 的 unit 多为中文硬编码。英文界面下按精确中文名映射为英文；
若 language yaml 提供 ``monitor_object_metric.<Object>.<metric>.enum``（id→译名），优先使用。
中文 locale 保持原样（或被 yaml enum 覆盖）。
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional

# 审定过的 Enum 标签中→英映射（精确匹配，避免误翻任意中文文案）。
_ENUM_ZH_TO_EN: dict[str, str] = {
    "正常": "Normal",
    "异常": "Abnormal",
    "未知": "Unknown",
    "成功": "Success",
    "失败": "Failure",
    "警告": "Warning",
    "告警": "Alert",
    "危险": "Critical",
    "严重": "Critical",
    "健康": "Healthy",
    "不健康": "Unhealthy",
    "不正常": "Abnormal",
    "通过": "Pass",
    "未通过": "Fail",
    "在位": "Present",
    "缺失": "Missing",
    "超时": "Timeout",
    "连接失败": "Connection Failed",
    "读取失败": "Read Failed",
    "返回不匹配": "Response Mismatch",
    "响应内容不匹配": "Content Mismatch",
    "响应体读取失败": "Body Read Error",
    "DNS错误": "DNS Error",
    "响应状态码不匹配": "Status Code Mismatch",
    "失活": "Inactive",
    "存活": "Alive",
    "部分失活": "Partially Inactive",
    "错误": "Error",
    "无法解析": "Unresolved",
    "未命中": "Not Found",
    "命中": "Found",
    "采集正常": "Scrape OK",
    "采集报错": "Scrape Error",
    "其它节点": "Other Broker",
    "首选Broker节点": "Preferred Broker",
    "副本不足": "Under-replicated",
    "提交偏移量大于LEO": "Committed Offset Ahead of LEO",
    "开机": "Power On",
    "关机": "Power Off",
    "工作": "Working",
    "停止": "Stopped",
    "启用": "Enabled",
    "禁用": "Disabled",
    "在线": "Online",
    "离线": "Offline",
    "就绪": "Ready",
    "不可用": "Unavailable",
    "静止": "Idle",
    "运行中": "Running",
    "无主节点": "No Leader",
    "有主节点": "Has Leader",
    "从节点": "Follower",
    "主节点": "Leader",
    "是": "Yes",
    "否": "No",
}


def _is_english_locale(locale: Optional[str]) -> bool:
    value = str(locale or "").strip().lower().replace("_", "-")
    return value == "en" or value.startswith("en-")


def _enum_id_key(value: Any) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def localize_metric_enum_unit(
    unit: str,
    locale: Optional[str] = None,
    *,
    enum_translations: Optional[Mapping[Any, Any]] = None,
) -> str:
    """本地化 Enum 指标的 unit JSON。非 Enum / 解析失败时原样返回。"""
    if not unit or not isinstance(unit, str):
        return unit
    stripped = unit.strip()
    if not stripped.startswith("["):
        return unit

    try:
        options = json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return unit
    if not isinstance(options, list):
        return unit

    yaml_map: dict[str, str] = {}
    if isinstance(enum_translations, Mapping):
        for key, value in enum_translations.items():
            if value is None:
                continue
            text = str(value).strip()
            if text:
                yaml_map[_enum_id_key(key)] = text

    english = _is_english_locale(locale)
    if not yaml_map and not english:
        return unit

    changed = False
    for option in options:
        if not isinstance(option, dict):
            continue
        name = option.get("name")
        if not isinstance(name, str):
            continue

        translated = yaml_map.get(_enum_id_key(option.get("id"))) if yaml_map else None
        if translated is None and english:
            translated = _ENUM_ZH_TO_EN.get(name)

        if translated is not None and translated != name:
            option["name"] = translated
            changed = True

    if not changed:
        return unit
    return json.dumps(options, ensure_ascii=False, separators=(",", ":"))
