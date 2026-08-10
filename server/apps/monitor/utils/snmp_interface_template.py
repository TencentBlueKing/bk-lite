"""SNMP 接口过滤的 UI / Jinja 单一真相源（运行时注入，避免各插件复制）。"""

from __future__ import annotations

import re
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

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

FILTER_JINJA_BLOCK = f"""\
{{% if enable_ifmib | default(true) %}}
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
        "description": (
            "留空表示不限制类型。非空时只保留所选 ifType；与排除列表互斥。填写后本配置中的非接口指标"
            "将不再采集，一般建议优先使用排除黑名单。"
        ),
        "description_en": ("Leave empty for no type restriction. Mutually exclusive with exclude list. Non-empty keeps only "
                           "matching interface metrics; non-interface metrics from this config will not be collected."),
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
SNMP_INPUT_RE = re.compile(r"^\s*\[\[inputs\.snmp\]\]", re.MULTILINE)

# 所有网络设备共用这一个 IF-MIB 模板；它仅声明 ifDescr tag，Telegraf walk 完整接口表。
COMMON_IFMIB_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "support-files/plugins/Telegraf/snmp/_common/ifmib.table.toml"
)


def get_common_ifmib_table_block() -> str:
    """从唯一通用 IF-MIB 模板读取接口表，供厂商单 child 配置复用。"""
    try:
        interface_table = COMMON_IFMIB_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"无法读取通用 IF-MIB 模板: {COMMON_IFMIB_TEMPLATE_PATH}") from exc
    if not IFMIB_HINT_RE.search(interface_table):
        raise RuntimeError(f"通用 IF-MIB 模板缺少接口表: {COMMON_IFMIB_TEMPLATE_PATH}")
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


def _strip_ifmib_tables(template_content: str) -> str:
    """删除各厂商复制的 IF-MIB table，绝不删除私有 OID table。"""

    def strip_table(table_match: re.Match[str]) -> str:
        table_text = table_match.group(0)
        return "" if IFMIB_HINT_RE.search(table_text) else table_text

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


def validate_rendered_core_network_ifmib(template_content: str, context: dict[str, Any]) -> None:
    """在下发前校验最终 SNMP TOML，拒绝公共 IF-MIB 与厂商配置的结构冲突。"""
    if not should_manage_core_network_ifmib(context) or not SNMP_INPUT_RE.search(template_content):
        return

    try:
        config = tomllib.loads(template_content)
    except tomllib.TOMLDecodeError as exc:
        message = "SNMP IF-MIB 配置冲突：最终 TOML 无法解析，请检查重复的接口表或 tagpass/tagdrop 段"
        raise ValidationAppException(f"{message}：{exc}") from exc

    interface_tables = [table for table in _get_snmp_input_tables(config) if table.get("name") == "interface"]
    enabled = context.get("enable_ifmib", True) is not False
    if enabled:
        if len(interface_tables) != 1:
            raise ValidationAppException(
                "SNMP IF-MIB 配置冲突：启用标准接口监控时必须且只能有一张接口表，"
                f"当前为 {len(interface_tables)} 张"
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

    for table in _get_snmp_input_tables(config):
        fields = table.get("field")
        if isinstance(fields, list) and any(field.get("name") == "ifType" for field in fields if isinstance(field, dict)):
            raise ValidationAppException("SNMP IF-MIB 配置冲突：关闭标准接口监控后仍渲染了 ifType 过滤标签")


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
        return enriched

    enriched["form_fields"].extend(get_ui_filter_fields(include_ifmib=include_ifmib))
    enriched["advanced_panel"] = get_ui_advanced_panel()
    return enriched
