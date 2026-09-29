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
# 脚本采集模板只允许绑在「操作系统」分类（id 在库内为 os / OS）。
SCRIPT_COLLECT_ALLOWED_OBJECT_TYPE_ID = "os"
SCRIPT_COLLECT_ALLOWED_OBJECT_TYPE_NAMES = frozenset({"操作系统", "os", "operating system"})
SCRIPT_COLLECT_OBJECT_TYPE_ERROR = "脚本采集模板仅允许绑定「操作系统」监控对象"


def is_script_collect_type(collect_type) -> bool:
    return str(collect_type or "").casefold() == SCRIPT_COLLECT_TYPE


def is_script_collect_allowed_object(monitor_object) -> bool:
    """创建脚本采集模板时，绑定对象必须属于操作系统分类。"""
    type_id = str(getattr(monitor_object, "type_id", None) or "").strip().casefold()
    if type_id == SCRIPT_COLLECT_ALLOWED_OBJECT_TYPE_ID:
        return True
    obj_type = getattr(monitor_object, "type", None)
    type_name = str(getattr(obj_type, "name", None) or "").strip().casefold()
    return type_name in SCRIPT_COLLECT_ALLOWED_OBJECT_TYPE_NAMES


# 平台保留标签。stdout / [inputs.bklite_script.tags] 不得作为最终来源。
RESERVED_SCRIPT_TAG_KEYS = (
    "instance_id",
    "instance_type",
    "collect_type",
    "config_type",
    "plugin_id",
    "agent_id",
    "script",
)
# 指标 ID 黑名单：保留标签 + config_id。不得并入 RESERVED_SCRIPT_TAG_KEYS（TOML 锁依赖该元组）。
RESERVED_SCRIPT_METRIC_NAMES = RESERVED_SCRIPT_TAG_KEYS + ("config_id",)
RESERVED_SCRIPT_METRIC_PREFIX = "bklite_script_"
RESERVED_SCRIPT_METRIC_NAME_ERROR = "指标 ID 与保留字段冲突，请更换"
SCRIPT_SELF_MONITOR_METRIC_NAMES = frozenset(
    {
        "up",
        "duration",
        "duration_ms",
        "duration_seconds",
        "exit_code",
        "run_duration",
        "bklite_script",
    }
)
SCRIPT_SELF_MONITOR_METRIC_DELETE_ERROR = "脚本自监控指标禁止删除"


def is_reserved_script_metric_name(name) -> bool:
    """指标 ID 不得占用平台保留标签名、config_id 或 bklite_script_ 前缀。"""
    text = str(name or "").strip()
    if not text:
        return False
    lower = text.casefold()
    if lower in {key.casefold() for key in RESERVED_SCRIPT_METRIC_NAMES}:
        return True
    return lower.startswith(RESERVED_SCRIPT_METRIC_PREFIX)


def is_script_self_monitor_metric_name(name, collect_type=None) -> bool:
    """脚本健康/自监控指标不可删：bklite_script_*，以及脚本插件下的 up / duration / exit_code。"""
    lower = str(name or "").strip().casefold()
    if not lower:
        return False
    if lower.startswith(RESERVED_SCRIPT_METRIC_PREFIX) or lower.startswith("bklite_script."):
        return True
    if is_script_collect_type(collect_type) and lower in SCRIPT_SELF_MONITOR_METRIC_NAMES:
        return True
    return False


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
    conflicts = []
    instance_id = ""
    instance_type = ""
    collect_type = ""
    config_type = ""
    plugin_id = ""
    agent_id = ""
    script = ""
    for k in metric.tags:
        if k == "instance_id":
            instance_id = metric.tags[k]
        elif k == "instance_type":
            instance_type = metric.tags[k]
        elif k == "collect_type":
            collect_type = metric.tags[k]
        elif k == "config_type":
            config_type = metric.tags[k]
        elif k == "plugin_id":
            plugin_id = metric.tags[k]
        elif k == "agent_id":
            agent_id = metric.tags[k]
        elif k == "script":
            script = metric.tags[k]
        elif k.startswith("bklite_script_"):
            conflicts.append(k)
    if instance_id != "" and instance_id != reserved_instance_id:
        conflicts.append("instance_id")
    if instance_type != "" and instance_type != reserved_instance_type:
        conflicts.append("instance_type")
    if collect_type != "" and collect_type != reserved_collect_type:
        conflicts.append("collect_type")
    if config_type != "" and config_type != reserved_config_type:
        conflicts.append("config_type")
    if plugin_id != "" and plugin_id != reserved_plugin_id:
        conflicts.append("plugin_id")
    if agent_id != "" and agent_id != reserved_agent_id:
        conflicts.append("agent_id")
    if script != "" and script != reserved_script:
        conflicts.append("script")
    metric.tags["instance_id"] = reserved_instance_id
    metric.tags["instance_type"] = reserved_instance_type
    metric.tags["collect_type"] = reserved_collect_type
    metric.tags["config_type"] = reserved_config_type
    metric.tags["plugin_id"] = reserved_plugin_id
    metric.tags["agent_id"] = reserved_agent_id
    metric.tags["script"] = reserved_script
    if len(conflicts) > 0:
        metric.tags["bklite_script_reserved_keys"] = ",".join(conflicts)
    return metric
'''

    [processors.starlark.constants]
        reserved_instance_id = "{{ instance_id }}"
        reserved_instance_type = "{{ instance_type }}"
        reserved_collect_type = "script"
        reserved_config_type = "script"
        reserved_plugin_id = "{{ plugin_id }}"
        reserved_agent_id = "${node.ip}-${node.cloud_region}"
        reserved_script = "default"
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
            "name": "script_os",
            "label": "操作系统",
            "label_en": "Operating System",
            "type": "segmented",
            "required": True,
            "default_value": "linux",
            "description": "决定解释器白名单与执行用户。Windows 以服务账号运行。",
            "description_en": "Selects the interpreter whitelist and run-as behavior. Windows uses the service account.",
            "options": [
                {"label": "Linux", "value": "linux"},
                {"label": "Windows", "value": "windows"},
            ],
            "transform_on_edit": {
                "origin_path": "child.content.config.script_os",
                "to_api": {},
            },
        },
        {
            "name": "interpreter",
            "label": "解释器",
            "label_en": "Interpreter",
            "type": "select",
            "required": True,
            "default_value": "/bin/sh",
            "description": "按操作系统从白名单选择解释器",
            "description_en": "Interpreter from the operating-system whitelist",
            "options": [
                {"label": "/bin/sh", "value": "/bin/sh"},
                {"label": "/bin/bash", "value": "/bin/bash"},
                {"label": "/usr/bin/python3", "value": "/usr/bin/python3"},
            ],
            "widget_props": {
                "placeholder": "选择解释器",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.interpreter",
                "to_api": {},
            },
        },
        {
            "name": "run_as",
            "label": "执行用户",
            "label_en": "Run As",
            "type": "input",
            "required": False,
            "default_value": "telegraf",
            "description": "Linux 必填，且不能为 root 或 UID 0。",
            "description_en": "Required on Linux. Cannot be root or UID 0.",
            "widget_props": {
                "placeholder": "telegraf",
            },
            "transform_on_edit": {
                "origin_path": "child.content.config.run_as",
                "to_api": {},
            },
        },
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
            child_template, _ = MonitorPluginConfigTemplate.objects.update_or_create(
                plugin=plugin,
                type=SCRIPT_CONFIG_TYPE,
                config_type="child",
                file_type="toml",
                defaults={"content": DEFAULT_SCRIPT_CHILD_TEMPLATE},
            )
            if child_template.content != DEFAULT_SCRIPT_CHILD_TEMPLATE:
                child_template.content = DEFAULT_SCRIPT_CHILD_TEMPLATE
                child_template.save(update_fields=["content", "updated_at"])
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
