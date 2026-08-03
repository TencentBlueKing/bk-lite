"""SNMP 接口维度过滤常量（与 UI default_value / 创建渲染默认注入同源）。"""

# 默认排除的 IANA ifType（页面「排除的接口类型」预填值；创建时由 plugin_controller 注入）
DEFAULT_IFTYPE_EXCLUDE = ["24", "53", "131", "135", "136"]

# 采集配置表单可选的常见 ifType（提交值为编号字符串）
IFTYPE_OPTIONS = [
    {"value": "6", "label": "6 - ethernetCsmacd", "label_en": "6 - ethernetCsmacd"},
    {"value": "24", "label": "24 - Loopback", "label_en": "24 - Loopback"},
    {"value": "53", "label": "53 - Virtual", "label_en": "53 - Virtual"},
    {"value": "117", "label": "117 - gigabitEthernet", "label_en": "117 - gigabitEthernet"},
    {"value": "131", "label": "131 - Tunnel", "label_en": "131 - Tunnel"},
    {"value": "135", "label": "135 - L2 VLAN", "label_en": "135 - L2 VLAN"},
    {"value": "136", "label": "136 - L3 VLAN", "label_en": "136 - L3 VLAN"},
    {"value": "161", "label": "161 - ieee8023adLag", "label_en": "161 - ieee8023adLag"},
]

IFTYPE_OID = "1.3.6.1.2.1.2.2.1.3"

# 模板 / 表单字段名
FIELD_IFTYPE_INCLUDE = "iftype_include"
FIELD_IFTYPE_EXCLUDE = "iftype_exclude"
FIELD_IFDESCR_INCLUDE = "ifdescr_include"
FIELD_IFDESCR_EXCLUDE = "ifdescr_exclude"

FILTER_TEMPLATE_VARS = (
    FIELD_IFTYPE_INCLUDE,
    FIELD_IFTYPE_EXCLUDE,
    FIELD_IFDESCR_INCLUDE,
    FIELD_IFDESCR_EXCLUDE,
)
