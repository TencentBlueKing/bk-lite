"""SNMP 接口过滤的 UI / Jinja 单一真相源（运行时注入，避免各插件复制）。"""

from __future__ import annotations

import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import toml
import tomllib

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.constants.snmp_interface import (
    DEFAULT_IFTYPE_EXCLUDE,
    FILTER_TEMPLATE_VARS,
    IFTYPE_OID,
    IFTYPE_OPTIONS,
)
from apps.monitor.utils.snmp_ifmib_capability import (
    is_ifmib_capable_plugin,
    is_ifmib_capable_render_context,
    is_interface_filter_capable_plugin,
)

FILTER_MARKER_BEGIN = "# ---- BK-Lite SNMP interface dimension filters (begin) ----"
FILTER_MARKER_END = "# ---- BK-Lite SNMP interface dimension filters (end) ----"

IFMIB_MARKER_BEGIN = "# ---- BK-Lite core IF-MIB collection (begin) ----"
IFMIB_MARKER_END = "# ---- BK-Lite core IF-MIB collection (end) ----"
# 编辑走 toml↔dict 会丢掉注释标记；用该旗标在写回时恢复关闭态，避免对账误回填。
BK_IFMIB_CLOSED_FLAG = "_bk_ifmib_closed"
COMMON_IFMIB_TABLE_PATH = Path(__file__).resolve().parents[1] / "support-files/plugins/Telegraf/snmp/_common/ifmib.table.toml"
PUBLIC_IFMIB_TABLE_OIDS = frozenset(
    {
        "1.3.6.1.2.1.2.2",
        "1.3.6.1.2.1.31.1.1",
        "IF-MIB::ifTable",
        "IF-MIB::ifXTable",
    }
)
PUBLIC_IFDESCR_OIDS = frozenset({"1.3.6.1.2.1.2.2.1.2", "1.3.6.1.2.1.31.1.1.1.1", "IF-MIB::ifDescr"})


def has_managed_ifmib_section(raw_content: str | None) -> bool:
    """渲染后的 child 是否包含公共 IF-MIB 管理区间（含 enable_ifmib=false 的空区间）。"""
    text = raw_content or ""
    return IFMIB_MARKER_BEGIN in text and IFMIB_MARKER_END in text


def _iter_content_snmp_inputs(content: dict) -> list[dict]:
    document = content.get("_toml_document") if isinstance(content, dict) else None
    if isinstance(document, dict):
        inputs = document.get("inputs")
        snmp_inputs = inputs.get("snmp") if isinstance(inputs, dict) else None
        if isinstance(snmp_inputs, list):
            return [item for item in snmp_inputs if isinstance(item, dict)]
        if isinstance(snmp_inputs, dict):
            return [snmp_inputs]
    config = content.get("config") if isinstance(content, dict) else None
    return [config] if isinstance(config, dict) else []


def content_has_public_ifmib_table(content: dict | None) -> bool:
    if not isinstance(content, dict):
        return False
    for snmp_input in _iter_content_snmp_inputs(content):
        tables = snmp_input.get("table")
        if not isinstance(tables, list):
            continue
        if any(isinstance(table, dict) and is_public_ifmib_table(table) for table in tables):
            return True
    return False


def mark_closed_ifmib_edit_state(raw_content: str | None, content: dict | None) -> dict | None:
    """读取配置时：关闭态（有管理区间且无公共表）打上可随表单回传的旗标。"""
    if not isinstance(content, dict):
        return content
    if has_managed_ifmib_section(raw_content) and not content_has_public_ifmib_table(content):
        content[BK_IFMIB_CLOSED_FLAG] = True
    else:
        content.pop(BK_IFMIB_CLOSED_FLAG, None)
    return content


def preserve_closed_ifmib_markers(toml_text: str | None, content: dict | None) -> str:
    """写回 TOML 时恢复关闭态管理区间，抵消注释在 dict roundtrip 中的丢失。"""
    text = toml_text or ""
    if not isinstance(content, dict) or not content.get(BK_IFMIB_CLOSED_FLAG):
        return text
    if content_has_public_ifmib_table(content):
        return text
    if has_managed_ifmib_section(text):
        return text
    return f"{IFMIB_MARKER_BEGIN}\n{IFMIB_MARKER_END}\n{text}"


@lru_cache(maxsize=1)
def _load_common_ifmib_table() -> dict[str, Any]:
    document = tomllib.loads(COMMON_IFMIB_TABLE_PATH.read_text(encoding="utf-8"))
    snmp_inputs = document.get("inputs", {}).get("snmp", [])
    if isinstance(snmp_inputs, dict):
        snmp_inputs = [snmp_inputs]
    for snmp_input in snmp_inputs:
        for table in snmp_input.get("table", []):
            if isinstance(table, dict) and table.get("name") == "interface":
                return table
    raise ValueError(f"通用 IF-MIB 模板缺少 interface 表: {COMMON_IFMIB_TABLE_PATH}")


def get_common_ifmib_table() -> dict[str, Any]:
    """返回公共 IF-MIB 表副本，供模板导入与存量配置回填共享。"""
    return deepcopy(_load_common_ifmib_table())


def is_public_ifmib_table(table: dict[str, Any]) -> bool:
    """只按标准表/字段 OID 识别公共 IF-MIB，名称本身不构成身份。"""
    table_oid = table.get("oid")
    if table_oid in PUBLIC_IFMIB_TABLE_OIDS:
        return True
    if table_oid not in (None, "") or table.get("name") != "interface":
        return False
    fields = table.get("field")
    return isinstance(fields, list) and any(
        isinstance(field, dict) and field.get("name") == "ifDescr" and field.get("oid") in PUBLIC_IFDESCR_OIDS
        for field in fields
    )


# 注意：不要在 IF-MIB table/field 之后裸写 tagexclude=。TOML 会把它绑到
# 最后一个 [[inputs.snmp.table.field]]，而不是 [[inputs.snmp]]。input 级
# tagexclude 由 ensure_public_ifmib_input_tagexclude 在渲染后补到 input 级。
FILTER_JINJA_BLOCK = f"""\
{{% if enable_ifmib | default(true) %}}
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
{{% endif %}}
"""

UI_ADVANCED_PANEL = {
    "title": "接口采集与过滤",
    "title_en": "Interface Collection and Filters",
    "hint": "控制标准 IF-MIB 接口指标采集，并可按接口类型（ifType）和名称（ifDescr）过滤",
    "hint_en": "Control standard IF-MIB collection and filter interfaces by ifType and ifDescr",
}

_UI_IFMIB_FIELD = {
    "name": "enable_ifmib",
    "label": "采集标准接口指标（IF-MIB）",
    "label_en": "Collect Standard Interface Metrics (IF-MIB)",
    "type": "switch",
    "required": True,
    "editable": True,
    "advanced": False,
    "default_value": True,
    "description": "默认开启。用于采集标准接口状态、流量、错包和丢包。",
    "description_en": "Enabled by default. Collects standard interface status, traffic, errors and discards.",
    "tooltip": (
        "建议开启：需要查看端口在线/关闭、接口速率与流量、错包或丢包时。\n\n"
        "采集指标：接口名称和类型（ifDescr、ifType）、管理/运行状态、接口速率、入/出字节、"
        "错误包、丢弃包、单播包，以及 64 位高速流量计数器（ifHCInOctets、ifHCOutOctets）。\n\n"
        "适用场景：大多数支持标准 SNMP IF-MIB 的网络设备；开启后可在下方按接口类型或名称过滤。\n\n"
        "建议关闭：设备不支持 IF-MIB、接口数量很大且只需厂商 CPU/内存/硬件健康指标，或希望减少采集量时。\n\n"
        "作用范围：仅影响本次下发。复用内置公共模板，不会创建第二份采集配置；"
        "关闭后厂商私有指标仍会采集。"
    ),
    "tooltip_en": (
        "Recommended when you need port up/down state, interface speed and traffic, errors, or discards.\n\n"
        "Metrics: interface name and type (ifDescr, ifType), admin/oper status, speed, inbound/outbound bytes, "
        "errors, discards, unicast packets, and 64-bit high-capacity traffic counters (ifHCInOctets, ifHCOutOctets).\n\n"
        "Use it for most network devices that support standard SNMP IF-MIB; when enabled, you can filter interfaces below by type or name.\n\n"
        "Turn it off when the device does not support IF-MIB, has too many interfaces and you need only vendor "
        "CPU/memory/hardware health, or you need to reduce collection volume.\n\n"
        "Scope: this deployment only. It reuses the built-in common template and does not create a second collector "
        "config. Vendor-private metrics remain collected when it is off."
    ),
}

_UI_INTERFACE_FILTER_MODE_FIELD = {
    "name": "interface_filter_mode",
    "label": "接口采集策略",
    "label_en": "Interface Collection Strategy",
    "type": "segmented",
    "required": False,
    "editable": True,
    "advanced": True,
    "section": "interface_filter",
    "default_value": "exclude",
    "description": "默认排除虚拟接口；切换策略会清空另一侧的过滤条件。",
    "description_en": "Virtual interfaces are excluded by default. Changing the strategy clears filters from the opposite strategy.",
    "options": [
        {"value": "all", "label": "全部采集", "label_en": "Collect All"},
        {"value": "exclude", "label": "排除部分", "label_en": "Exclude Some"},
        {"value": "include", "label": "仅采集部分", "label_en": "Include Only"},
    ],
    "dependency": {"field": "enable_ifmib", "value": True},
}

_UI_FILTER_FIELDS: list[dict[str, Any]] = [
    _UI_INTERFACE_FILTER_MODE_FIELD,
    {
        "name": "iftype_exclude",
        "label": "排除的接口类型（ifType）",
        "label_en": "Excluded Interface Types (ifType)",
        "type": "select",
        "required": False,
        "advanced": True,
        "section": "interface_filter",
        "default_value": list(DEFAULT_IFTYPE_EXCLUDE),
        "description": ("默认排除 Loopback/Virtual/Tunnel/L2VLAN/L3VLAN；清空则不再按类型排除。"
                        "与「仅采集」互斥，不可选择相同类型。"),
        "description_en": ("Defaults exclude Loopback/Virtual/Tunnel/L2VLAN/L3VLAN. Clear to disable type exclusion. "
                           "Mutually exclusive with include list."),
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
        "description": ("留空表示不限制类型。非空时只保留所选 ifType；与排除列表互斥。"
                        "过滤仅作用于公共接口指标，厂商 CPU、内存和硬件健康指标仍会采集。"),
        "description_en": ("Leave empty for no type restriction. Mutually exclusive with exclude list. Non-empty keeps only "
                           "matching interface metrics; vendor CPU, memory, and hardware-health metrics remain collected."),
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
        "description": ("逗号分隔，支持通配符，例如 Loopback*,Vlan*,Null*。与「仅采集」名称列表互斥，"
                        "不可填写相同条目。"),
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
        "description": ("留空表示不限制名称。非空时只保留名称匹配的接口；与排除名称列表互斥。"
                        "与 ifType 白名单同时填写时需同时命中（AND）。"),
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
IFMIB_HINT_RE = re.compile(
    r'name\s*=\s*"ifDescr"|oid\s*=\s*"1\.3\.6\.1\.2\.1\.(?:2\.2|31\.1\.1)"',
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
INPUT_TAGEXCLUDE_KEY_RE = re.compile(r"^[ \t]*tagexclude\s*=", re.MULTILINE)
SNMP_INPUT_RE = re.compile(r"^\s*\[\[inputs\.snmp\]\]", re.MULTILINE)


def get_common_ifmib_table_block() -> str:
    """从唯一通用 IF-MIB 模板读取接口表，供厂商单 child 配置复用。"""
    try:
        interface_table = COMMON_IFMIB_TABLE_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"无法读取通用 IF-MIB 模板: {COMMON_IFMIB_TABLE_PATH}") from exc
    if not IFMIB_HINT_RE.search(interface_table):
        raise RuntimeError(f"通用 IF-MIB 模板缺少接口表: {COMMON_IFMIB_TABLE_PATH}")
    return interface_table


def get_common_ifmib_jinja_block() -> str:
    return (
        f"{IFMIB_MARKER_BEGIN}\n"
        "{% if enable_ifmib | default(true) %}\n"
        f"{get_common_ifmib_table_block()}\n"
        f"{IFTYPE_FIELD_BLOCK.rstrip()}\n"
        "{% endif %}\n"
        f"{IFMIB_MARKER_END}"
    )


def get_ui_filter_fields(include_ifmib: bool = False) -> list[dict[str, Any]]:
    fields = [deepcopy(_UI_IFMIB_FIELD)] if include_ifmib else []
    fields.extend(deepcopy(_UI_FILTER_FIELDS))
    for field in fields:
        if field.get("name") in FILTER_TEMPLATE_VARS:
            if not include_ifmib:
                field.pop("dependency", None)
                continue
            mode = "include" if field["name"].endswith("_include") else "exclude"
            field["dependency"] = {
                "field": ["enable_ifmib", "interface_filter_mode"],
                "conditions": [[{"equals": True}], [{"equals": mode}]],
            }
    return fields


def get_ui_advanced_panel() -> dict[str, Any]:
    return deepcopy(UI_ADVANCED_PANEL)


def has_interface_collection(template_content: str) -> bool:
    return bool(INTERFACE_HINT_RE.search(template_content or ""))


def _table_block_header_value(table_text: str, key: str) -> str | None:
    header = table_text.split("[[inputs.snmp.table.field]]", 1)[0]
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"\s*$', header, re.MULTILINE)
    return match.group(1) if match else None


def is_public_ifmib_table_block(table_text: str) -> bool:
    """渲染文本层面的公共表判定，与 is_public_ifmib_table 的 OID 口径保持一致。"""
    table_oid = _table_block_header_value(table_text, "oid")
    if table_oid in PUBLIC_IFMIB_TABLE_OIDS:
        return True
    if table_oid not in (None, "") or _table_block_header_value(table_text, "name") != "interface":
        return False
    return any(
        re.search(rf'^\s*oid\s*=\s*"{re.escape(ifdescr_oid)}"\s*$', table_text, re.MULTILINE)
        for ifdescr_oid in PUBLIC_IFDESCR_OIDS
    )


def _strip_ifmib_tables(template_content: str) -> str:
    """删除各厂商复制的 IF-MIB table，绝不删除私有 OID table。"""

    def strip_table(table_match: re.Match[str]) -> str:
        table_text = table_match.group(0)
        return "" if is_public_ifmib_table_block(table_text) else table_text

    text = TABLE_BLOCK_RE.sub(strip_table, template_content)
    text = re.sub(
        re.escape(IFMIB_MARKER_BEGIN) + r".*?" + re.escape(IFMIB_MARKER_END) + r"\n?",
        "",
        text,
        flags=re.DOTALL,
    )
    return re.sub(r"\n{3,}", "\n\n", text)


def should_manage_core_network_ifmib(context: dict[str, Any]) -> bool:
    return is_ifmib_capable_render_context(context)


def ensure_core_network_ifmib_jinja(template_content: str, context: dict[str, Any]) -> str:
    """复用通用 SNMP 模板的 IF-MIB 表，厂商模板仅保留私有 OID。"""
    if not should_manage_core_network_ifmib(context):
        return template_content

    text = _strip_ifmib_tables(template_content)
    return f"{text.rstrip()}\n\n{get_common_ifmib_jinja_block()}\n"


def _get_snmp_input_tables(config: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = config.get("inputs")
    if not isinstance(inputs, dict):
        return []
    snmp_inputs = inputs.get("snmp")
    if not isinstance(snmp_inputs, list):
        return []
    return [table for snmp_input in snmp_inputs if isinstance(snmp_input, dict) for table in snmp_input.get("table", []) if isinstance(table, dict)]


def ensure_public_ifmib_input_tagexclude(
    template_content: str,
    context: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> str:
    """把 ifType tagexclude 补到承载公共 IF-MIB 的 [[inputs.snmp]] 头部。

    TOML 不允许在 table/field 之后用裸键回到 input 级，所以渲染后按文本插入而不是
    走 toml 往返：保留 IF-MIB 管理区间等注释，也不会因厂商模板语法问题抛解析异常。
    能力边界与公共 IF-MIB 一致，非 Network Device 模板不得被静默加上 ifType 排除。
    """
    if not force:
        context = context or {}
        if not should_manage_core_network_ifmib(context) or context.get("enable_ifmib", True) is False:
            return template_content

    text = template_content or ""
    headers = list(SNMP_INPUT_RE.finditer(text))
    if not headers:
        return text

    insert_positions: list[tuple[int, str]] = []
    for index, header in enumerate(headers):
        segment_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        segment = text[header.start() : segment_end]
        if not any(is_public_ifmib_table_block(match.group(0)) for match in TABLE_BLOCK_RE.finditer(segment)):
            continue
        header_line_end = segment.find("\n")
        if header_line_end == -1:
            continue
        body = segment[header_line_end + 1 :]
        first_section = re.search(r"^[ \t]*\[", body, re.MULTILINE)
        input_level = body[: first_section.start()] if first_section else body
        if INPUT_TAGEXCLUDE_KEY_RE.search(input_level):
            continue
        indent_match = re.search(r"^([ \t]+)\S", input_level, re.MULTILINE)
        indent = indent_match.group(1) if indent_match else "    "
        insert_positions.append((header.start() + header_line_end + 1, f'{indent}tagexclude = ["ifType"]\n'))

    if not insert_positions:
        return text
    for position, line in reversed(insert_positions):
        text = f"{text[:position]}{line}{text[position:]}"
    return text


def validate_rendered_core_network_ifmib(template_content: str, context: dict[str, Any]) -> None:
    """在下发前校验最终 SNMP TOML，拒绝公共 IF-MIB 与厂商配置的结构冲突。"""
    if not should_manage_core_network_ifmib(context) or not SNMP_INPUT_RE.search(template_content):
        return

    try:
        config = tomllib.loads(template_content)
    except tomllib.TOMLDecodeError as exc:
        message = "SNMP IF-MIB 配置冲突：最终 TOML 无法解析，请检查重复的接口表或 tagpass/tagdrop 段"
        raise ValidationAppException(f"{message}：{exc}") from exc

    snmp_inputs = config.get("inputs", {}).get("snmp", []) if isinstance(config.get("inputs"), dict) else []
    if isinstance(snmp_inputs, dict):
        snmp_inputs = [snmp_inputs]
    interface_tables = [table for table in _get_snmp_input_tables(config) if is_public_ifmib_table(table)]
    enabled = context.get("enable_ifmib", True) is not False
    if enabled:
        if len(interface_tables) != 1:
            raise ValidationAppException(
                "SNMP IF-MIB 配置冲突：启用标准接口监控时必须且只能有一张接口表，"
                f"当前为 {len(interface_tables)} 张"
            )

        public_owners = [
            snmp_input
            for snmp_input in snmp_inputs
            if isinstance(snmp_input, dict)
            and any(isinstance(table, dict) and is_public_ifmib_table(table) for table in snmp_input.get("table", []) or [])
        ]
        if not any(
            isinstance(owner.get("tagexclude"), list) and "ifType" in owner["tagexclude"] for owner in public_owners
        ):
            raise ValidationAppException(
                "SNMP IF-MIB 配置冲突：公共接口采集缺少 inputs.snmp 级 tagexclude=[\"ifType\"]"
            )
        for owner in public_owners:
            for table in owner.get("table", []) or []:
                if not isinstance(table, dict):
                    continue
                for field in table.get("field", []) or []:
                    if isinstance(field, dict) and "tagexclude" in field:
                        raise ValidationAppException(
                            "SNMP IF-MIB 配置冲突：tagexclude 误绑在 table.field 上，必须位于 inputs.snmp"
                        )

        fields = interface_tables[0].get("field")
        if not isinstance(fields, list):
            raise ValidationAppException("SNMP IF-MIB 配置冲突：公共接口表缺少字段定义")
        field_names = [field.get("name") for field in fields if isinstance(field, dict)]
        if len(field_names) != len(set(field_names)):
            raise ValidationAppException("SNMP IF-MIB 配置冲突：公共接口表存在重复字段")
        if field_names.count("ifType") != 1:
            raise ValidationAppException("SNMP IF-MIB 配置冲突：公共接口表必须且只能包含一个 ifType 过滤标签")
        return

    if interface_tables:
        raise ValidationAppException("SNMP IF-MIB 配置冲突：关闭标准接口监控后仍渲染了接口表")


def restore_managed_ifmib_markers(template_content: str) -> str:
    """在 toml 往返后把公共 IF-MIB 表重新包进管理区间标记。"""
    text = template_content or ""
    if has_managed_ifmib_section(text):
        return text
    headers = list(SNMP_INPUT_RE.finditer(text))
    wraps: list[tuple[int, int]] = []
    for index, header in enumerate(headers):
        segment_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        segment = text[header.start() : segment_end]
        public_blocks = [
            match
            for match in TABLE_BLOCK_RE.finditer(segment)
            if is_public_ifmib_table_block(match.group(0))
        ]
        if not public_blocks:
            continue
        wraps.append((header.start() + public_blocks[0].start(), header.start() + public_blocks[-1].end()))
    for start, end in reversed(wraps):
        chunk = text[start:end].strip("\n")
        text = f"{text[:start]}{IFMIB_MARKER_BEGIN}\n{chunk}\n{IFMIB_MARKER_END}\n{text[end:]}"
    return text


def isolate_snmp_interface_tagpass(
    template_content: str,
    context: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> str:
    """白名单仅作用于公共接口 input，避免丢弃没有接口标签的厂商指标。

    force=True 用于编辑写回：不依赖渲染 context，只要检测到 tagpass 与厂商表混在
    同一 inputs.snmp 就拆分。
    """
    if not force:
        context = context or {}
        if not should_manage_core_network_ifmib(context) or context.get("enable_ifmib", True) is False:
            return template_content

    document = toml.loads(template_content)
    snmp_inputs = document.get("inputs", {}).get("snmp", [])
    if isinstance(snmp_inputs, dict):
        snmp_inputs = [snmp_inputs]
        document.setdefault("inputs", {})["snmp"] = snmp_inputs
    for index, snmp_input in enumerate(snmp_inputs):
        if not isinstance(snmp_input, dict) or not isinstance(snmp_input.get("tagpass"), dict):
            continue
        if not snmp_input["tagpass"]:
            continue
        tables = snmp_input.get("table")
        if not isinstance(tables, list):
            continue
        interface_tables = [table for table in tables if isinstance(table, dict) and is_public_ifmib_table(table)]
        if not interface_tables:
            continue

        input_payload_keys = {"field", "table", "tagexclude", "tagpass", "tagdrop"}
        interface_input = {key: deepcopy(value) for key, value in snmp_input.items() if key not in input_payload_keys}
        source_fields = [deepcopy(field) for field in snmp_input.get("field", []) if isinstance(field, dict) and field.get("is_tag") is True]
        if source_fields:
            interface_input["field"] = source_fields
        interface_input["table"] = interface_tables
        for filter_key in ("tagexclude", "tagpass", "tagdrop"):
            if filter_key in snmp_input:
                interface_input[filter_key] = deepcopy(snmp_input.pop(filter_key))

        remaining_tables = [table for table in tables if table not in interface_tables]
        source_payload_fields = snmp_input.get("field")
        has_non_tag_fields = isinstance(source_payload_fields, list) and any(
            not isinstance(field, dict) or field.get("is_tag") is not True
            for field in source_payload_fields
        )
        if remaining_tables:
            snmp_input["table"] = remaining_tables
        else:
            snmp_input.pop("table", None)

        if remaining_tables or has_non_tag_fields:
            snmp_inputs.insert(index + 1, interface_input)
        else:
            # 原 input 仅承载公共接口表（以及已复制的 tag 字段）时直接替换，
            # 避免生成一个没有任何采集载荷的额外 inputs.snmp。
            snmp_inputs[index] = interface_input
        rendered = toml.dumps(document).replace("[inputs]\n", "")
        # toml.dumps 会丢掉注释；管理区间标记必须写回，否则对账无法识别关闭态。
        return restore_managed_ifmib_markers(rendered)
    return template_content


def should_inject_snmp_interface_filters(plugin: Any, content: dict | None = None) -> bool:
    """仅对会渲染公共 IF-MIB 表的网络设备注入接口过滤 UI。"""
    # 过滤依赖公共接口表内的 ifDescr / ifType。不能仅凭「这是 SNMP」就注入，
    # 否则未采集接口指标的模板会出现无效过滤项。
    return is_interface_filter_capable_plugin(plugin)


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

    # 核心网络模板的公共 IF-MIB 条件块已在同一块内声明 ifType；再次用
    # 正则插入会跨越 Jinja endif，把字段遗留在关闭块之外。
    text = template_content if IFMIB_MARKER_BEGIN in template_content else ensure_iftype_tag_fields(template_content)
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


def merge_snmp_interface_filter_ui(content: dict | None, plugin: Any = None) -> dict | None:
    """用常量四字段 + advanced_panel 覆盖/补齐 UI 模板（SNMP 运行时注入）。"""
    if not content:
        return content

    enriched = content
    form_fields = enriched.get("form_fields")
    if not isinstance(form_fields, list):
        form_fields = []
        enriched["form_fields"] = form_fields

    include_ifmib = is_ifmib_capable_plugin(plugin)
    include_filters = is_interface_filter_capable_plugin(plugin)
    filter_names = set(FILTER_TEMPLATE_VARS) | {"enable_ifmib", "interface_filter_mode"}
    kept = [
        field
        for field in form_fields
        if not (isinstance(field, dict) and field.get("name") in filter_names)
    ]
    enriched["form_fields"] = kept
    if not include_filters:
        panel = enriched.get("advanced_panel")
        if isinstance(panel, dict) and panel.get("title") == UI_ADVANCED_PANEL["title"]:
            enriched.pop("advanced_panel", None)
        return enriched

    enriched["form_fields"].extend(get_ui_filter_fields(include_ifmib=include_ifmib))
    enriched["advanced_panel"] = get_ui_advanced_panel()
    return enriched
