"""自定义 SNMP 模板的对象无关默认蓝图。"""

from copy import deepcopy

CUSTOM_SNMP_CONFIG_TYPE = "custom_snmp"

DEFAULT_CUSTOM_SNMP_COLLECT_SNIPPET = """# [[inputs.snmp.field]]
#   oid = ".1.3.6.1.2.1.1.3.0"
#   name = "snmp_uptime"
#
# [[inputs.snmp.table]]
#   oid = ".1.3.6.1.2.1.2.2"
#   name = "interface"
#
#   [[inputs.snmp.table.field]]
#     oid = ".1.3.6.1.2.1.2.2.1.2"
#     name = "ifDescr"
#     is_tag = true"""

DEFAULT_CUSTOM_SNMP_CHILD_TEMPLATE = (
    """[[inputs.snmp]]
    startup_error_behavior = "retry"
    interval = "{{ interval }}s"
    agents = ["udp://{{ ip }}:{{ port }}"]
{% if version == 2 %}
    version = 2
    community = "{{ community }}"
    timeout = "{{ timeout }}s"
{% elif version == 3 %}
    version = 3
    timeout = "{{ timeout }}s"
    sec_name = "{{ sec_name }}"
    sec_level = "{{ sec_level }}"
    auth_protocol = "{{ auth_protocol }}"
    auth_password = "{{ auth_password }}"
    priv_protocol = "{{ priv_protocol }}"
    priv_password = "{{ priv_password }}"
{% endif %}
    [inputs.snmp.tags]
        instance_id = "{{ instance_id }}"
        instance_type = "{{ instance_type }}"
        collect_type = "snmp"
        config_type = "custom_snmp"
        plugin_id = "{{ plugin_id }}"
{# BK_LITE_SNMP_COLLECT_START #}
"""
    + DEFAULT_CUSTOM_SNMP_COLLECT_SNIPPET
    + """
{# BK_LITE_SNMP_COLLECT_END #}
"""
)


DEFAULT_CUSTOM_SNMP_UI_TEMPLATE = {
    "object_name": "",
    "instance_type": "",
    "collect_type": "snmp",
    "config_type": [CUSTOM_SNMP_CONFIG_TYPE],
    "collector": "Telegraf",
    "instance_id": "{{cloud_region}}_{{instance_type}}_snmp_{{ip}}",
    "form_fields": [
        {
            "name": "ip",
            "label": "IP",
            "label_en": "IP",
            "type": "input",
            "required": True,
            "visible_in": "edit",
            "editable": False,
            "description": "监控目标的 IP 地址。",
            "description_en": "IP address of the monitored target.",
            "widget_props": {"placeholder": "目标 IP", "placeholder_en": "Target IP"},
            "transform_on_edit": {
                "origin_path": "child.content.config.agents[0]",
                "to_form": {"regex": "://([^:]+):"},
            },
        },
        {
            "name": "port",
            "label": "端口",
            "label_en": "Port",
            "type": "inputNumber",
            "required": True,
            "editable": False,
            "default_value": 161,
            "description": "SNMP 服务端口，通常为 161。",
            "description_en": "SNMP service port, usually 161.",
            "widget_props": {"min": 1, "max": 65535, "placeholder": "SNMP 端口", "placeholder_en": "SNMP port"},
            "transform_on_edit": {
                "origin_path": "child.content.config.agents[0]",
                "to_form": {"regex": ":(\\d+)$"},
            },
        },
        {
            "name": "version",
            "label": "版本",
            "label_en": "Version",
            "type": "select",
            "required": True,
            "editable": False,
            "default_value": 2,
            "options": [{"label": "v2c", "value": 2}, {"label": "v3", "value": 3}],
            "widget_props": {"placeholder": "选择 SNMP 版本", "placeholder_en": "Select SNMP version"},
            "transform_on_edit": {"origin_path": "child.content.config.version"},
        },
        {
            "name": "community",
            "label": "团体名",
            "label_en": "Community",
            "type": "input",
            "required": True,
            "default_value": "public",
            "dependency": {"field": "version", "value": 2},
            "widget_props": {"placeholder": "SNMP Community", "placeholder_en": "SNMP community"},
            "transform_on_edit": {"origin_path": "child.content.config.community", "to_api": {}},
        },
        {
            "name": "sec_name",
            "label": "安全名称",
            "label_en": "Security Name",
            "type": "input",
            "required": True,
            "dependency": {"field": "version", "value": 3},
            "widget_props": {"placeholder": "安全名称", "placeholder_en": "Security name"},
            "transform_on_edit": {"origin_path": "child.content.config.sec_name", "to_api": {}},
        },
        {
            "name": "sec_level",
            "label": "安全级别",
            "label_en": "Security Level",
            "type": "select",
            "required": True,
            "default_value": "authPriv",
            "dependency": {"field": "version", "value": 3},
            "options": [
                {"label": "noAuthNoPriv", "value": "noAuthNoPriv"},
                {"label": "authNoPriv", "value": "authNoPriv"},
                {"label": "authPriv", "value": "authPriv"},
            ],
            "widget_props": {"placeholder": "选择安全级别", "placeholder_en": "Select security level"},
            "transform_on_edit": {"origin_path": "child.content.config.sec_level", "to_api": {}},
        },
        {
            "name": "auth_protocol",
            "label": "认证协议",
            "label_en": "Auth Protocol",
            "type": "input",
            "required": False,
            "default_value": "SHA",
            "dependency": {
                "field": ["version", "sec_level"],
                "conditions": [[{"equals": 3}], [{"in": ["authNoPriv", "authPriv"]}]],
            },
            "widget_props": {"placeholder": "MD5/SHA", "placeholder_en": "MD5/SHA"},
            "transform_on_edit": {"origin_path": "child.content.config.auth_protocol", "to_api": {}},
        },
        {
            "name": "auth_password",
            "label": "认证密码",
            "label_en": "Auth Password",
            "type": "password",
            "required": False,
            "dependency": {
                "field": ["version", "sec_level"],
                "conditions": [[{"equals": 3}], [{"in": ["authNoPriv", "authPriv"]}]],
            },
            "widget_props": {"placeholder": "认证密码", "placeholder_en": "Auth password"},
            "transform_on_edit": {"origin_path": "child.content.config.auth_password", "to_api": {}},
        },
        {
            "name": "priv_protocol",
            "label": "加密协议",
            "label_en": "Privacy Protocol",
            "type": "input",
            "required": False,
            "default_value": "AES",
            "dependency": {
                "field": ["version", "sec_level"],
                "conditions": [[{"equals": 3}], [{"equals": "authPriv"}]],
            },
            "widget_props": {"placeholder": "DES/AES", "placeholder_en": "DES/AES"},
            "transform_on_edit": {"origin_path": "child.content.config.priv_protocol", "to_api": {}},
        },
        {
            "name": "priv_password",
            "label": "加密密码",
            "label_en": "Privacy Password",
            "type": "password",
            "required": False,
            "dependency": {
                "field": ["version", "sec_level"],
                "conditions": [[{"equals": 3}], [{"equals": "authPriv"}]],
            },
            "widget_props": {"placeholder": "加密密码", "placeholder_en": "Privacy password"},
            "transform_on_edit": {"origin_path": "child.content.config.priv_password", "to_api": {}},
        },
        {
            "name": "timeout",
            "label": "超时时间",
            "label_en": "Timeout",
            "type": "inputNumber",
            "required": True,
            "default_value": 10,
            "widget_props": {"min": 1, "placeholder": "超时时间", "placeholder_en": "Timeout", "addonAfter": "s"},
            "transform_on_edit": {
                "origin_path": "child.content.config.timeout",
                "to_form": {"regex": "^(\\d+)s$"},
                "to_api": {"suffix": "s"},
            },
        },
        {
            "name": "interval",
            "label": "采集间隔",
            "label_en": "Collection Interval",
            "type": "inputNumber",
            "required": True,
            "default_value": 60,
            "widget_props": {
                "min": 1,
                "precision": 0,
                "placeholder": "采集间隔",
                "placeholder_en": "Collection interval",
                "addonAfter": "s",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.interval",
                "to_form": {"regex": "^(\\d+)s$"},
                "to_api": {"suffix": "s"},
            },
        },
    ],
    "table_columns": [
        {
            "name": "node_ids",
            "label": "节点",
            "label_en": "Node",
            "type": "select",
            "required": True,
            "options_key": "node_ids_option",
            "enable_row_filter": False,
            "widget_props": {"placeholder": "请选择节点", "placeholder_en": "Select node"},
        },
        {
            "name": "ip",
            "label": "IP",
            "label_en": "IP",
            "type": "input",
            "required": True,
            "widget_props": {"placeholder": "请输入 IP 地址", "placeholder_en": "Enter IP address"},
            "change_handler": {"type": "simple", "source_fields": ["ip"], "target_field": "instance_name"},
        },
        {
            "name": "instance_name",
            "label": "实例名称",
            "label_en": "Instance Name",
            "type": "input",
            "required": True,
            "widget_props": {"placeholder": "实例名称", "placeholder_en": "Instance name"},
        },
        {
            "name": "group_ids",
            "label": "组",
            "label_en": "Group",
            "type": "group_select",
            "required": True,
            "widget_props": {"placeholder": "请选择组", "placeholder_en": "Select group"},
        },
    ],
    "extra_edit_fields": {
        "agents": {
            "origin_path": "child.content.config.agents",
            "to_api": {"template": "udp://{{ip}}:{{port}}", "array": True},
        }
    },
}


def build_default_custom_snmp_ui_template(monitor_object) -> dict:
    """按监控对象实例化通用 SNMP 接入表单。"""
    content = deepcopy(DEFAULT_CUSTOM_SNMP_UI_TEMPLATE)
    content["object_name"] = monitor_object.name
    content["instance_type"] = monitor_object.name
    return content
