"""脚本采集 child 模板：inputs.exec 之后强制覆盖平台保留标签。"""

from apps.monitor.utils.plugin_controller import Controller


SCRIPT_COLLECT_TYPE = "script"
SCRIPT_CONFIG_TYPE = "script"

# 平台保留标签。stdout / [inputs.exec.tags] 不得作为最终来源。
RESERVED_SCRIPT_TAG_KEYS = (
    "instance_id",
    "instance_type",
    "collect_type",
    "config_type",
    "plugin_id",
    "agent_id",
)

# name_prefix + namepass 按 config_id 隔离，避免合并进同一 Telegraf 后改写其他采集。
DEFAULT_SCRIPT_CHILD_TEMPLATE = """[[inputs.exec]]
    startup_error_behavior = "retry"
    commands = ["{{ command }}"]
    timeout = "{{ timeout | default(10, true) }}s"
    interval = "{{ interval }}s"
    data_format = "influx"
    name_prefix = "bklite_script_{{ config_id }}_"
    [inputs.exec.tags]
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


class CustomScriptPluginService:
    @staticmethod
    def child_template() -> str:
        return DEFAULT_SCRIPT_CHILD_TEMPLATE

    @staticmethod
    def render_child_template(context: dict) -> str:
        return Controller({}).render_template(
            DEFAULT_SCRIPT_CHILD_TEMPLATE,
            context,
            escape_toml_strings=True,
        )
