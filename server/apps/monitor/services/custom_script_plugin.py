"""脚本采集 child 模板：inputs.bklite_script 之后强制覆盖平台保留标签。"""

import copy

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.utils.instance_id_keys import resolve_metric_instance_id_keys
from apps.monitor.utils.plugin_controller import Controller

SCRIPT_COLLECT_TYPE = "script"
SCRIPT_CONFIG_TYPE = "script"

# 平台保留标签。stdout / [inputs.bklite_script.tags] 不得作为最终来源。
RESERVED_SCRIPT_TAG_KEYS = (
    "instance_id",
    "instance_type",
    "collect_type",
    "config_type",
    "plugin_id",
    "agent_id",
)

# name_prefix + namepass 按 config_id 隔离，避免合并进同一 Telegraf 后改写其他采集。
# 插件契约：script 为脚本正文（可从旧字段 command 迁入）；timeout / data_format /
# command / commands / script_file 不下发。interval 由平台传秒，模板拼 "Ns"；
# 子进程 timeout 由插件按 interval-1s 推导。
DEFAULT_SCRIPT_CHILD_TEMPLATE = """[[inputs.bklite_script]]
    interval = "{{ interval }}s"
    interpreter = "{{ interpreter | default('/bin/sh', true) }}"
    script = "{{ script }}"
    {% if script_env %}script_env = "{{ script_env }}"{% endif %}
    {% if params %}params = {{ params | to_toml_str_array }}{% endif %}
    {% if environment %}environment = {{ environment | to_toml_str_array }}{% endif %}
    {% if run_as %}run_as = "{{ run_as }}"{% endif %}
    {% if script_name %}script_name = "{{ script_name }}"{% endif %}
    name_prefix = "bklite_script_{{ config_id }}_"
    [inputs.bklite_script.tags]
        instance_id = "{{ instance_id }}"
        instance_type = "{{ instance_type }}"
        collect_type = "script"
        config_type = "script"
        plugin_id = "{{ plugin_id }}"

[[processors.starlark]]
    namepass = ["bklite_script_{{ config_id }}_*"]
    source = '''
def apply(metric):
    metric.tags["instance_id"] = reserved_instance_id
    metric.tags["instance_type"] = reserved_instance_type
    metric.tags["collect_type"] = reserved_collect_type
    metric.tags["config_type"] = reserved_config_type
    metric.tags["plugin_id"] = reserved_plugin_id
    metric.tags["agent_id"] = reserved_agent_id
    return metric
'''

    [processors.starlark.constants]
        reserved_instance_id = "{{ instance_id }}"
        reserved_instance_type = "{{ instance_type }}"
        reserved_collect_type = "script"
        reserved_config_type = "script"
        reserved_plugin_id = "{{ plugin_id }}"
        reserved_agent_id = "${node.ip}-${node.cloud_region}"
"""


DEFAULT_SCRIPT_UI_TEMPLATE = {
    "object_name": "",
    "instance_type": "",
    "collect_type": SCRIPT_COLLECT_TYPE,
    "config_type": [SCRIPT_CONFIG_TYPE],
    "collector": "Telegraf",
    "support_collect_detect": True,
    "instance_id": "{{cloud_region}}_{{instance_type}}_script_{{instance_name}}",
    "form_fields": [
        {
            "name": "script",
            "label": "脚本内容",
            "label_en": "Script Body",
            "type": "textarea",
            "required": True,
            "description": "监控采集执行的脚本正文",
            "description_en": "Script body to execute for collection",
            "widget_props": {
                "placeholder": "粘贴或输入脚本内容",
                "rows": 6,
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.script",
                "to_api": {},
            },
        },
        {
            "name": "interpreter",
            "label": "解释器",
            "label_en": "Interpreter",
            "type": "input",
            "required": True,
            "default_value": "/bin/sh",
            "description": "脚本执行解释器，例如 /bin/sh、/bin/bash、/usr/bin/python3",
            "description_en": "Script execution interpreter, e.g. /bin/sh, /bin/bash, /usr/bin/python3",
            "widget_props": {
                "placeholder": "/bin/sh",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.interpreter",
                "to_api": {},
            },
        },
        {
            "name": "interval",
            "label": "采集间隔",
            "label_en": "Interval",
            "type": "inputNumber",
            "required": True,
            "default_value": 60,
            "description": "监控数据的采集时间间隔（单位：秒，最低 60 秒）",
            "description_en": "Collection interval in seconds (min 60s)",
            "widget_props": {
                "min": 60,
                "precision": 0,
                "placeholder": "间隔",
                "placeholder_en": "Interval",
                "addonAfter": "s",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.interval",
                "to_form": {"regex": r"^(\d+)s$"},
                "to_api": {"suffix": "s"},
            },
        },
        {
            "name": "run_as",
            "label": "执行用户 (Linux)",
            "label_en": "Run As (Linux)",
            "type": "input",
            "required": False,
            "default_value": "telegraf",
            "description": "Linux 节点执行脚本的用户（禁止 root 或 UID 0，默认 telegraf）；Windows 节点将忽略此配置并以服务账号运行。",
            "description_en": (
                "User to execute the script on Linux nodes (cannot be root or UID 0, default telegraf); "
                "Windows nodes will run as the service account."
            ),
            "widget_props": {
                "placeholder": "telegraf",
            },
            "rules": [
                {
                    "type": "pattern",
                    "pattern": r"^(?!^root$|^0+$).+$",
                    "message": "不允许以 root 运行",
                }
            ],
            "transform_on_edit": {
                "origin_path": "child.content.config.run_as",
                "to_api": {},
            },
        },
        {
            "name": "environment",
            "label": "环境变量",
            "label_en": "Environment",
            "type": "key_value_list",
            "required": False,
            "description": "脚本运行时的环境变量（KEY=VALUE）",
            "description_en": "Environment variables for the script (KEY=VALUE)",
            "transform_on_create": {
                "type": "key_value_env_array",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.environment",
                "to_form": {"type": "key_value_list"},
                "to_api": {"type": "key_value_env_array"},
            },
        },
        {
            "name": "params",
            "label": "脚本参数",
            "label_en": "Script Parameters",
            "type": "input",
            "required": False,
            "description": "脚本命令行参数，多个参数用逗号分隔",
            "description_en": "Script command-line parameters, comma separated",
            "widget_props": {
                "placeholder": "arg1, arg2",
            },
            "transform_on_create": {
                "split": ",",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.params",
                "to_api": {"split": ","},
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
            "widget_props": {"placeholder": "请选择节点", "placeholder_en": "Select node"},
            "enable_row_filter": False,
        },
        {
            "name": "instance_name",
            "label": "实例名称",
            "label_en": "Instance Name",
            "type": "input",
            "required": True,
            "widget_props": {"placeholder": "请输入实例名称", "placeholder_en": "Enter instance name"},
            "is_only": True,
        },
        {
            "name": "group_ids",
            "label": "组",
            "label_en": "Group",
            "type": "group_select",
            "required": False,
            "widget_props": {"placeholder": "请选择组", "placeholder_en": "Select group"},
        },
    ],
    "extra_edit_fields": {},
}


SCRIPT_HEALTH_METRICS = [
    {
        "name": "bklite_script_up",
        "display_name": "脚本运行状态",
        "query": "bklite_script_up{__$labels__}",
        "unit": "",
        "data_type": "Number",
        "description": "脚本采集执行状态（1=正常，0=异常）",
        "sort_order": 0,
    },
    {
        "name": "bklite_script_duration_seconds",
        "display_name": "脚本执行耗时",
        "query": "bklite_script_duration_seconds{__$labels__}",
        "unit": "s",
        "data_type": "Number",
        "description": "脚本单次执行耗时（秒）",
        "sort_order": 1,
    },
    {
        "name": "bklite_script_exit_code",
        "display_name": "脚本退出码",
        "query": "bklite_script_exit_code{__$labels__}",
        "unit": "",
        "data_type": "Number",
        "description": "脚本执行进程退出码（0 表示成功）",
        "sort_order": 2,
    },
]


def _child_render_context(context: dict) -> dict:
    """渲染键以 script 为准；仅当 script 为空时把旧字段 command 迁入 script。"""
    render_context = dict(context)
    if str(render_context.get("script") or "").strip():
        return render_context
    command = render_context.get("command")
    if command not in (None, ""):
        render_context["script"] = command
    return render_context


class CustomScriptPluginService:
    @staticmethod
    def child_template() -> str:
        return DEFAULT_SCRIPT_CHILD_TEMPLATE

    @staticmethod
    def render_child_template(context: dict) -> str:
        return Controller({}).render_template(
            DEFAULT_SCRIPT_CHILD_TEMPLATE,
            _child_render_context(context),
            escape_toml_strings=True,
        )

    @staticmethod
    def initialize_templates(plugin: MonitorPlugin):
        monitor_object = plugin.monitor_object.all().order_by("id").first()
        if monitor_object is None:
            raise BaseAppException("自定义脚本模板必须绑定一个监控对象")

        ui_template = copy.deepcopy(DEFAULT_SCRIPT_UI_TEMPLATE)
        ui_template["object_name"] = monitor_object.name
        ui_template["instance_type"] = monitor_object.name

        with transaction.atomic():
            MonitorPluginConfigTemplate.objects.update_or_create(
                plugin=plugin,
                type=SCRIPT_CONFIG_TYPE,
                config_type="child",
                file_type="toml",
                defaults={"content": DEFAULT_SCRIPT_CHILD_TEMPLATE},
            )
            MonitorPluginUITemplate.objects.update_or_create(
                plugin=plugin,
                defaults={"content": ui_template},
            )

            metric_group, _ = MetricGroup.objects.get_or_create(
                monitor_object=monitor_object,
                monitor_plugin=plugin,
                name="Base",
                defaults={
                    "description": "基础指标",
                    "is_pre": False,
                    "sort_order": 0,
                },
            )

            instance_id_keys = resolve_metric_instance_id_keys(
                [],
                monitor_object.instance_id_keys,
                strict=False,
            ) or ["instance_id"]

            for item in SCRIPT_HEALTH_METRICS:
                Metric.objects.update_or_create(
                    monitor_object=monitor_object,
                    monitor_plugin=plugin,
                    name=item["name"],
                    defaults={
                        "metric_group": metric_group,
                        "display_name": item["display_name"],
                        "query": item["query"],
                        "unit": item["unit"],
                        "data_type": item["data_type"],
                        "description": item["description"],
                        "dimensions": [],
                        "instance_id_keys": instance_id_keys,
                        "is_pre": False,
                        "sort_order": item.get("sort_order", 0),
                    },
                )
