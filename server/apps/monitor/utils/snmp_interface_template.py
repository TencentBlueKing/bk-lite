"""SNMP 接口过滤的 UI / Jinja 单一真相源（运行时注入，避免各插件复制）。"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from apps.monitor.constants.snmp_interface import (
    DEFAULT_IFTYPE_EXCLUDE,
    FILTER_TEMPLATE_VARS,
    IFTYPE_OID,
    IFTYPE_OPTIONS,
)

FILTER_MARKER_BEGIN = "# ---- BK-Lite SNMP interface dimension filters (begin) ----"
FILTER_MARKER_END = "# ---- BK-Lite SNMP interface dimension filters (end) ----"

FILTER_JINJA_BLOCK = f"""\
    tagexclude = ["ifType"]
{FILTER_MARKER_BEGIN}
{{# ifType/ifDescr 黑白名单：空规则不输出对应键；默认排除由页面/创建注入，模板不做静默 fallback #}}
{{# 使用 |default 而非 is defined：采集沙箱 Environment 清空了 Jinja tests #}}
{{% set _iftype_include = iftype_include | default('', true) %}}
{{% set _iftype_exclude = iftype_exclude | default('', true) %}}
{{% set _ifdescr_include = ifdescr_include | default('', true) %}}
{{% set _ifdescr_exclude = ifdescr_exclude | default('', true) %}}
{{% if _iftype_include or _ifdescr_include %}}
    [inputs.snmp.tagpass]
{{% if _iftype_include %}}
        ifType = {{{{ _iftype_include | to_toml_str_array }}}}
{{% endif %}}
{{% if _ifdescr_include %}}
        ifDescr = {{{{ _ifdescr_include | to_toml_str_array }}}}
{{% endif %}}
{{% endif %}}
{{% if _iftype_exclude or _ifdescr_exclude %}}
    [inputs.snmp.tagdrop]
{{% if _iftype_exclude %}}
        ifType = {{{{ _iftype_exclude | to_toml_str_array }}}}
{{% endif %}}
{{% if _ifdescr_exclude %}}
        ifDescr = {{{{ _ifdescr_exclude | to_toml_str_array }}}}
{{% endif %}}
{{% endif %}}
{FILTER_MARKER_END}
"""

UI_ADVANCED_PANEL = {
    "title": "接口过滤",
    "title_en": "Interface Filters",
    "hint": "按接口类型（ifType）和名称（ifDescr）配置排除或仅采集",
    "hint_en": "Configure exclude or include filters by ifType and ifDescr",
}

_UI_FILTER_FIELDS: list[dict[str, Any]] = [
    {
        "name": "iftype_exclude",
        "label": "排除的接口类型（ifType）",
        "label_en": "Excluded Interface Types (ifType)",
        "type": "select",
        "required": False,
        "advanced": True,
        "section": "interface_filter",
        "default_value": list(DEFAULT_IFTYPE_EXCLUDE),
        "description": "默认排除 Loopback/Virtual/Tunnel/L2VLAN/L3VLAN；清空则不再按类型排除。与「仅采集」互斥，不可选择相同类型。",
        "description_en": "Defaults exclude Loopback/Virtual/Tunnel/L2VLAN/L3VLAN. Clear to disable type exclusion. Mutually exclusive with include list.",
        "options": IFTYPE_OPTIONS,
        "widget_props": {
            "mode": "tags",
            "allowClear": True,
            "tokenSeparators": [","],
            "placeholder": "选择常用类型，或输入数字（如 22）后回车",
            "placeholder_en": "Select a common type, or type a number (e.g. 22) and press Enter",
        },
        "rules": [
            {
                "type": "mutex_with",
                "field": "iftype_include",
                "message": "排除与仅采集的接口类型存在冲突，请勿同时选择：{{conflicts}}",
                "message_en": "Excluded and included ifType values conflict: {{conflicts}}",
            }
        ],
        "transform_on_edit": {
            "origin_path": "child.content.config.tagdrop.ifType",
            "to_api": {},
        },
    },
    {
        "name": "iftype_include",
        "label": "仅采集的接口类型（ifType）",
        "label_en": "Included Interface Types (ifType)",
        "type": "select",
        "required": False,
        "advanced": True,
        "section": "interface_filter",
        "default_value": [],
        "description": "留空表示不限制类型。非空时只保留所选 ifType；与排除列表互斥。填写后本配置中的非接口指标将不再采集，一般建议优先使用排除黑名单。",
        "description_en": "Leave empty for no type restriction. Mutually exclusive with exclude list. Non-empty keeps only matching interface metrics; non-interface metrics from this config will not be collected.",
        "options": IFTYPE_OPTIONS,
        "widget_props": {
            "mode": "tags",
            "allowClear": True,
            "tokenSeparators": [","],
            "placeholder": "选择常用类型，或输入数字（如 22）后回车；留空不限制",
            "placeholder_en": "Select a common type, or type a number (e.g. 22); empty = all types",
        },
        "rules": [
            {
                "type": "mutex_with",
                "field": "iftype_exclude",
                "message": "排除与仅采集的接口类型存在冲突，请勿同时选择：{{conflicts}}",
                "message_en": "Excluded and included ifType values conflict: {{conflicts}}",
            }
        ],
        "transform_on_edit": {
            "origin_path": "child.content.config.tagpass.ifType",
            "to_api": {},
        },
    },
    {
        "name": "ifdescr_exclude",
        "label": "排除的接口名称（ifDescr）",
        "label_en": "Excluded Interface Names (ifDescr)",
        "type": "input",
        "required": False,
        "advanced": True,
        "section": "interface_filter",
        "default_value": "",
        "description": "逗号分隔，支持通配符，例如 Loopback*,Vlan*,Null*。与「仅采集」名称列表互斥，不可填写相同条目。",
        "description_en": "Comma-separated globs, e.g. Loopback*,Vlan*,Null*. Mutually exclusive with include name list.",
        "widget_props": {
            "placeholder": "例如 Loopback*,Vlan*,Null*",
            "placeholder_en": "e.g. Loopback*,Vlan*,Null*",
        },
        "rules": [
            {
                "type": "mutex_with",
                "field": "ifdescr_include",
                "message": "排除与仅采集的接口名称存在冲突，请勿同时填写：{{conflicts}}",
                "message_en": "Excluded and included ifDescr values conflict: {{conflicts}}",
            }
        ],
        "transform_on_edit": {
            "origin_path": "child.content.config.tagdrop.ifDescr",
            "to_form": {"array_join": ","},
            "to_api": {"split": ","},
        },
    },
    {
        "name": "ifdescr_include",
        "label": "仅采集的接口名称（ifDescr）",
        "label_en": "Included Interface Names (ifDescr)",
        "type": "input",
        "required": False,
        "advanced": True,
        "section": "interface_filter",
        "default_value": "",
        "description": "留空表示不限制名称。非空时只保留名称匹配的接口；与排除名称列表互斥。与 ifType 白名单同时填写时需同时命中（AND）。",
        "description_en": "Leave empty for no name restriction. Mutually exclusive with exclude name list. Combined with ifType include uses AND.",
        "widget_props": {
            "placeholder": "不限制；例如 GigabitEthernet*,Eth-Trunk*",
            "placeholder_en": "No restriction; e.g. GigabitEthernet*,Eth-Trunk*",
        },
        "rules": [
            {
                "type": "mutex_with",
                "field": "ifdescr_exclude",
                "message": "排除与仅采集的接口名称存在冲突，请勿同时填写：{{conflicts}}",
                "message_en": "Excluded and included ifDescr values conflict: {{conflicts}}",
            }
        ],
        "transform_on_edit": {
            "origin_path": "child.content.config.tagpass.ifDescr",
            "to_form": {"array_join": ","},
            "to_api": {"split": ","},
        },
    },
]

IFTYPE_FIELD_BLOCK = f"""\
    [[inputs.snmp.table.field]]
        oid = "{IFTYPE_OID}"
        name = "ifType"
        is_tag = true
"""

INTERFACE_HINT_RE = re.compile(
    r'name\s*=\s*"ifDescr"|oid\s*=\s*"1\.3\.6\.1\.2\.1\.2\.2"|oid\s*=\s*"1\.3\.6\.1\.2\.1\.31\.1\.1"',
    re.MULTILINE,
)
TABLE_BLOCK_RE = re.compile(
    r"^[ \t]*\[\[inputs\.snmp\.table\]\][^\n]*\n.*?"
    r"(?=^[ \t]*\[\[(?!inputs\.snmp\.table\.field\]\])|\Z)",
    re.MULTILINE | re.DOTALL,
)
FIELD_BLOCK_RE = re.compile(
    r"^[ \t]*\[\[inputs\.snmp\.table\.field\]\][^\n]*\n.*?(?=^[ \t]*\[\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
PROCESSORS_RE = re.compile(r"^\[\[processors\.", re.MULTILINE)
FILTER_BLOCK_RE = re.compile(
    re.escape(FILTER_MARKER_BEGIN) + r".*?" + re.escape(FILTER_MARKER_END) + r"\n?",
    re.DOTALL,
)
TAGEXCLUDE_IFTYPE_RE = re.compile(r'^\s*tagexclude\s*=\s*\["ifType"\]\s*\n', re.MULTILINE)


def get_ui_filter_fields() -> list[dict[str, Any]]:
    return deepcopy(_UI_FILTER_FIELDS)


def get_ui_advanced_panel() -> dict[str, Any]:
    return deepcopy(UI_ADVANCED_PANEL)


def has_interface_collection(template_content: str) -> bool:
    return bool(INTERFACE_HINT_RE.search(template_content or ""))


def should_inject_snmp_interface_filters(plugin: Any, content: dict | None = None) -> bool:
    """判断是否应注入接口过滤 UI（collect_type / 表单指纹 / 插件目录）。"""
    if plugin is not None and getattr(plugin, "collect_type", None) == "snmp":
        return True

    if isinstance(content, dict):
        names = {
            str(field.get("name") or "")
            for field in (content.get("form_fields") or [])
            if isinstance(field, dict)
        }
        if {"port", "version", "community"} <= names:
            return True
        if {"port", "version", "sec_name"} <= names:
            return True

    if plugin is not None:
        try:
            from apps.monitor.services.plugin_guide import PluginGuideService

            plugin_dir = PluginGuideService.resolve_plugin_dir(plugin)
        except Exception:
            plugin_dir = None
        if plugin_dir is not None and "snmp" in Path(plugin_dir).parts:
            return True
    return False


def needs_snmp_interface_filter_jinja(template_content: str) -> bool:
    text = template_content or ""
    return has_interface_collection(text) or FILTER_MARKER_BEGIN in text


def ensure_iftype_tag_fields(template_content: str) -> str:
    """幂等：在每个 ifDescr 采集字段后注入 ifType tag，供 tagpass/tagdrop 使用。"""
    if not has_interface_collection(template_content):
        return template_content

    def ensure_table(table_match: re.Match[str]) -> str:
        table_text = table_match.group(0)
        fields = list(FIELD_BLOCK_RE.finditer(table_text))
        ifdescr = next(
            (field for field in fields if re.search(r'^\s*name\s*=\s*"ifDescr"\s*$', field.group(0), re.MULTILINE)),
            None,
        )
        if ifdescr is None:
            return table_text
        if any(
            re.search(r'^\s*name\s*=\s*"ifType"\s*$', field.group(0), re.MULTILINE)
            or re.search(
                rf'^\s*oid\s*=\s*"{re.escape(IFTYPE_OID)}"\s*$',
                field.group(0),
                re.MULTILINE,
            )
            for field in fields
        ):
            return table_text
        insert_at = ifdescr.end()
        before = table_text[:insert_at].rstrip("\n")
        after = table_text[insert_at:].lstrip("\n")
        injected = f"{before}\n{IFTYPE_FIELD_BLOCK.rstrip()}"
        return f"{injected}\n{after}" if after else f"{injected}\n"

    return TABLE_BLOCK_RE.sub(ensure_table, template_content)


def ensure_snmp_interface_filter_jinja(template_content: str) -> str:
    """幂等：注入 ifType OID 字段 + 过滤 Jinja 片段（单一真相源）。"""
    if not needs_snmp_interface_filter_jinja(template_content):
        return template_content

    text = ensure_iftype_tag_fields(template_content)
    text = FILTER_BLOCK_RE.sub("", text)
    text = TAGEXCLUDE_IFTYPE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    processors = PROCESSORS_RE.search(text)
    insert_at = processors.start() if processors else len(text)
    before = text[:insert_at].rstrip("\n")
    after = text[insert_at:].lstrip("\n")
    block = FILTER_JINJA_BLOCK.strip("\n")
    if after:
        return f"{before}\n\n{block}\n\n{after}"
    return f"{before}\n\n{block}\n"


def merge_snmp_interface_filter_ui(content: dict | None) -> dict | None:
    """用常量四字段 + advanced_panel 覆盖/补齐 UI 模板（SNMP 运行时注入）。"""
    if not content:
        return content

    enriched = content
    form_fields = enriched.get("form_fields")
    if not isinstance(form_fields, list):
        form_fields = []
        enriched["form_fields"] = form_fields

    filter_names = set(FILTER_TEMPLATE_VARS)
    kept = [
        field
        for field in form_fields
        if not (isinstance(field, dict) and field.get("name") in filter_names)
    ]
    kept.extend(get_ui_filter_fields())
    enriched["form_fields"] = kept
    enriched["advanced_panel"] = get_ui_advanced_panel()
    return enriched
