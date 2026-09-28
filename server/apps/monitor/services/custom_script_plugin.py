"""脚本采集 child 模板：经平台 wrapper 执行，并在 exec 之后强制覆盖平台保留标签。"""

from apps.monitor.utils.plugin_controller import Controller


SCRIPT_COLLECT_TYPE = "script"
SCRIPT_CONFIG_TYPE = "script"

LINUX_SCRIPT_WRAPPER_PATH = "/opt/fusion-collectors/bin/bklite-script-wrapper"
WINDOWS_SCRIPT_WRAPPER_PATH = r"C:\fusion-collectors\bin\bklite-script-wrapper.exe"

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
# inputs.exec 只调用平台 wrapper；脚本正文与参数走环境变量，不进 argv。
DEFAULT_SCRIPT_CHILD_TEMPLATE = """[[inputs.exec]]
    startup_error_behavior = "retry"
    commands = ["{{ wrapper_path }}"]
    timeout = "{{ timeout | default(10, true) }}s"
    interval = "{{ interval }}s"
    data_format = "prometheus"
    name_prefix = "bklite_script_{{ config_id }}_"
    environment = ["BK_SCRIPT_CONFIG_ID={{ config_id }}", "BK_SCRIPT_INSTANCE_ID={{ instance_id }}", "BK_SCRIPT_TIMEOUT={{ timeout | default(10, true) }}", "BK_SCRIPT_USER={{ username }}", "BK_SCRIPT_ALLOW_ROOT={{ allow_root | default(0, true) }}", "BK_SCRIPT_BODY=${SCRIPT_BODY__{{ config_id }}}", "BK_SCRIPT_INTERPRETER=${SCRIPT_INTERPRETER__{{ config_id }}}"]
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


def script_wrapper_path(operating_system: str | None) -> str:
    if str(operating_system or "").strip().lower() == "windows":
        return WINDOWS_SCRIPT_WRAPPER_PATH
    return LINUX_SCRIPT_WRAPPER_PATH


class CustomScriptPluginService:
    @staticmethod
    def child_template() -> str:
        return DEFAULT_SCRIPT_CHILD_TEMPLATE

    @staticmethod
    def render_child_template(context: dict) -> str:
        ctx = dict(context or {})
        if not str(ctx.get("wrapper_path") or "").strip():
            ctx["wrapper_path"] = script_wrapper_path(ctx.get("operating_system") or ctx.get("os_type"))
        return Controller({}).render_template(
            DEFAULT_SCRIPT_CHILD_TEMPLATE,
            ctx,
            escape_toml_strings=True,
        )
