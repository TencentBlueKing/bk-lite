import copy
import re
from urllib.parse import urlparse
from typing import Optional

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.safe_jinja import contains_template_syntax
from apps.monitor.models import CollectConfig, MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
from apps.monitor.utils.config_format import ConfigFormat
from apps.monitor.utils.plugin_controller import Controller
from apps.rpc.node_mgmt import NodeMgmt


SNMP_COLLECT_MARKER_START = "{# BK_LITE_SNMP_COLLECT_START #}"
SNMP_COLLECT_MARKER_END = "{# BK_LITE_SNMP_COLLECT_END #}"
SNMP_COLLECT_PATTERN = re.compile(
    rf"{re.escape(SNMP_COLLECT_MARKER_START)}\n?(.*?)\n?{re.escape(SNMP_COLLECT_MARKER_END)}",
    re.S,
)
SNMP_SECTION_START_PATTERN = re.compile(r"^\s*\[\[inputs\.snmp\.(?:field|table)\]\]\s*$", re.M)
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


class CustomSnmpPluginService:
    @staticmethod
    def get_monitor_object(plugin: MonitorPlugin):
        monitor_object = plugin.monitor_object.all().order_by("id").first()
        if monitor_object is None:
            raise BaseAppException("自定义SNMP模板必须绑定一个监控对象")
        return monitor_object

    @staticmethod
    def get_builtin_plugin(plugin: MonitorPlugin):
        monitor_object = CustomSnmpPluginService.get_monitor_object(plugin)
        builtin_plugins = list(
            MonitorPlugin.objects.filter(
                monitor_object=monitor_object,
                collector="Telegraf",
                collect_type="snmp",
                template_type="builtin",
            ).order_by("id")
        )
        if not builtin_plugins:
            raise BaseAppException("当前监控对象暂无可复用的 SNMP 内置模板")
        if len(builtin_plugins) > 1:
            raise BaseAppException("当前监控对象存在多份 SNMP 内置模板，请联系管理员处理")
        return builtin_plugins[0]

    @staticmethod
    def _get_snmp_section_bounds(content: str) -> tuple[int, int]:
        match = SNMP_SECTION_START_PATTERN.search(content)
        if not match:
            raise BaseAppException("SNMP 子配置模板缺少可编辑的采集片段")
        return match.start(), len(content)

    @staticmethod
    def _inject_collect_markers(content: str) -> str:
        if SNMP_COLLECT_PATTERN.search(content):
            return content
        start, end = CustomSnmpPluginService._get_snmp_section_bounds(content)
        snippet = content[start:end].strip("\n")
        prefix = content[:start].rstrip("\n")
        suffix = content[end:].lstrip("\n")
        parts = [prefix, SNMP_COLLECT_MARKER_START, snippet, SNMP_COLLECT_MARKER_END]
        if suffix:
            parts.append(suffix)
        return "\n".join(part for part in parts if part != "") + "\n"

    @staticmethod
    def _require_collect_marker_match(content: str):
        marker_match = SNMP_COLLECT_PATTERN.search(content)
        if not marker_match:
            raise BaseAppException("当前 SNMP 模板缺少可编辑片段标记，请重新创建模板")
        return marker_match

    @staticmethod
    def _extract_collect_snippet(content: str) -> str:
        marker_match = CustomSnmpPluginService._require_collect_marker_match(content)
        return marker_match.group(1).strip("\n")

    @staticmethod
    def _replace_collect_snippet(content: str, snippet: str) -> str:
        normalized_snippet = snippet.strip("\n")
        CustomSnmpPluginService._require_collect_marker_match(content)
        return SNMP_COLLECT_PATTERN.sub(
            f"{SNMP_COLLECT_MARKER_START}\n{normalized_snippet}\n{SNMP_COLLECT_MARKER_END}",
            content,
            count=1,
        )

    @staticmethod
    def _clone_templates(source_plugin: MonitorPlugin, target_plugin: MonitorPlugin):
        for template in MonitorPluginConfigTemplate.objects.filter(plugin=source_plugin).order_by("id"):
            content = template.content
            if template.config_type == "child":
                content = CustomSnmpPluginService._inject_collect_markers(content)
                content = CustomSnmpPluginService._replace_collect_snippet(content, DEFAULT_CUSTOM_SNMP_COLLECT_SNIPPET)
            MonitorPluginConfigTemplate.objects.update_or_create(
                plugin=target_plugin,
                type=template.type,
                config_type=template.config_type,
                file_type=template.file_type,
                defaults={"content": content},
            )

        ui_template = MonitorPluginUITemplate.objects.filter(plugin=source_plugin).first()
        if ui_template:
            MonitorPluginUITemplate.objects.update_or_create(
                plugin=target_plugin,
                defaults={"content": copy.deepcopy(ui_template.content)},
            )

    @staticmethod
    def initialize_templates(plugin: MonitorPlugin):
        source_plugin = CustomSnmpPluginService.get_builtin_plugin(plugin)

        with transaction.atomic():
            CustomSnmpPluginService._clone_templates(source_plugin, plugin)

            update_fields = []
            if not (plugin.status_query or "").strip() and (source_plugin.status_query or "").strip():
                plugin.status_query = source_plugin.status_query
                update_fields.append("status_query")
            if not (plugin.description or "").strip() and (source_plugin.description or "").strip():
                plugin.description = source_plugin.description
                update_fields.append("description")
            if not plugin.node_selector and source_plugin.node_selector:
                plugin.node_selector = copy.deepcopy(source_plugin.node_selector)
                update_fields.append("node_selector")
            if update_fields:
                plugin.save(update_fields=[*update_fields, "updated_at"])

    @staticmethod
    def get_child_template(plugin: MonitorPlugin):
        child_templates = list(MonitorPluginConfigTemplate.objects.filter(plugin=plugin, config_type="child").order_by("id"))
        if not child_templates:
            raise BaseAppException("当前 SNMP 模板缺少采集配置")
        if len(child_templates) > 1:
            raise BaseAppException("当前 SNMP 模板存在多份采集配置，请联系管理员处理")
        return child_templates[0]

    @staticmethod
    def get_collect_template(plugin: MonitorPlugin):
        child_template = CustomSnmpPluginService.get_child_template(plugin)
        return {
            "plugin_id": plugin.id,
            "template_id": plugin.template_id,
            "display_name": plugin.display_name or plugin.name,
            "content": CustomSnmpPluginService._extract_collect_snippet(child_template.content),
            "type": child_template.type,
            "config_type": child_template.config_type,
            "file_type": child_template.file_type,
        }

    @staticmethod
    def _normalize_duration(value):
        if isinstance(value, str) and value.endswith("s"):
            return value[:-1]
        return value

    @staticmethod
    def _parse_ip_port(agent: Optional[str]) -> tuple[str, int]:
        if not agent:
            raise BaseAppException("实例采集配置缺少 SNMP agent 配置")
        parsed = urlparse(agent)
        if not parsed.hostname or parsed.port is None:
            raise BaseAppException("实例采集配置中的 SNMP agent 格式无效")
        return parsed.hostname, parsed.port

    @staticmethod
    def _build_validation_context(plugin: MonitorPlugin, child_template: MonitorPluginConfigTemplate):
        monitor_object = CustomSnmpPluginService.get_monitor_object(plugin)
        return {
            "interval": 10,
            "timeout": 10,
            "version": 2,
            "ip": "127.0.0.1",
            "port": 161,
            "community": "public",
            "sec_name": "snmp-user",
            "sec_level": "authPriv",
            "auth_protocol": "SHA",
            "auth_password": "auth-password",
            "priv_protocol": "AES",
            "priv_password": "priv-password",
            "instance_id": ["sample-instance"],
            "instance_type": monitor_object.name.lower(),
            "type": child_template.type,
            "config_id": "SNMPVALIDATION",
            "plugin_id": plugin.template_id,
            "monitor_plugin_id": plugin.template_id,
        }

    @staticmethod
    def _validate_child_template(plugin: MonitorPlugin, child_template: MonitorPluginConfigTemplate, template_content: str):
        controller = Controller({})
        rendered_content = controller.render_template(
            template_content,
            CustomSnmpPluginService._build_validation_context(plugin, child_template),
        )
        try:
            ConfigFormat.toml_to_dict(rendered_content)
        except Exception as exc:
            raise BaseAppException(f"采集片段格式校验失败: {exc}") from exc

    @staticmethod
    def _build_propagation_plan(plugin: MonitorPlugin, template_content: str, child_template: MonitorPluginConfigTemplate):
        config_objs = list(CollectConfig.objects.filter(monitor_plugin=plugin, is_child=True).order_by("id"))
        if not config_objs:
            return []

        node_mgmt = NodeMgmt()
        controller = Controller({})
        update_plan = []
        child_config_map = {item["id"]: item for item in node_mgmt.get_child_configs_by_ids([config_obj.id for config_obj in config_objs])}

        expected_config_ids = []

        for config_obj in config_objs:
            if config_obj.config_type != child_template.type or config_obj.file_type != child_template.file_type:
                raise BaseAppException(f"实例 {config_obj.id} 的采集配置类型与模板不匹配")

            expected_config_ids.append(config_obj.id)

            child_config = child_config_map.get(config_obj.id)
            if not child_config:
                raise BaseAppException(f"未找到实例 {config_obj.id} 的已下发采集配置")
            render_context = CustomSnmpPluginService._build_child_render_context(config_obj, child_config, plugin.template_id)
            try:
                rendered_content = controller.render_template(template_content, render_context)
            except Exception as exc:
                raise BaseAppException(f"实例 {config_obj.id} 的采集配置渲染失败: {exc}") from exc
            try:
                ConfigFormat.toml_to_dict(rendered_content)
            except Exception as exc:
                raise BaseAppException(f"实例 {config_obj.id} 的采集配置渲染失败: {exc}") from exc

            update_plan.append(
                {
                    "id": config_obj.id,
                    "original_content": child_config.get("content") or "",
                    "rendered_content": rendered_content,
                }
            )

        if len(update_plan) != len(expected_config_ids):
            raise BaseAppException("采集模板同步计划生成不完整，请稍后重试")

        return update_plan

    @staticmethod
    def _rollback_propagation(node_mgmt: NodeMgmt, applied_updates: list[dict]):
        rollback_failures = []
        for item in reversed(applied_updates):
            try:
                node_mgmt.update_child_config_content(item["id"], item["original_content"])
            except Exception:
                rollback_failures.append(item["id"])
        return rollback_failures

    @staticmethod
    def _build_child_render_context(config_obj: CollectConfig, child_config: dict, plugin_template_id: str):
        child_content = child_config.get("content") or ""
        parsed_content = ConfigFormat.toml_to_dict(child_content)
        config = copy.deepcopy(parsed_content.get("config") or {})
        tags = config.get("tags") or {}
        agents = config.get("agents") or []
        ip, port = CustomSnmpPluginService._parse_ip_port(agents[0] if agents else "")

        config["ip"] = ip
        config["port"] = port
        config["instance_id"] = tags.get("instance_id", "")
        config["instance_type"] = tags.get("instance_type", "")
        config["interval"] = CustomSnmpPluginService._normalize_duration(config.get("interval"))
        config["timeout"] = CustomSnmpPluginService._normalize_duration(config.get("timeout"))
        config["type"] = config_obj.config_type
        config["config_id"] = config_obj.id.upper()
        config["plugin_id"] = plugin_template_id
        config["monitor_plugin_id"] = plugin_template_id
        return config

    @staticmethod
    def propagate_collect_template(update_plan: list[dict]):
        if not update_plan:
            return
        node_mgmt = NodeMgmt()
        applied_updates = []
        try:
            for item in update_plan:
                node_mgmt.update_child_config_content(item["id"], item["rendered_content"])
                applied_updates.append(item)
        except Exception as exc:
            rollback_failures = CustomSnmpPluginService._rollback_propagation(node_mgmt, applied_updates)
            rollback_tip = f"；以下实例回滚可能未完成: {', '.join(rollback_failures)}" if rollback_failures else ""
            raise BaseAppException(f"采集模板同步失败: {exc}{rollback_tip}") from exc

    @staticmethod
    def update_collect_template(plugin: MonitorPlugin, snippet: str):
        normalized_snippet = (snippet or "").strip()
        if not normalized_snippet:
            raise BaseAppException("采集片段不能为空")
        if "[[inputs.snmp]]" in normalized_snippet or "[inputs.snmp.tags]" in normalized_snippet:
            raise BaseAppException("仅支持编辑 SNMP 指标采集片段，请勿修改 inputs.snmp 主配置")
        # 安全校验：采集片段为 SNMP 指标 TOML，不应包含模板表达式或反射用的双下划线，防止 SSTI/RCE
        if contains_template_syntax(normalized_snippet) or "__" in normalized_snippet:
            raise BaseAppException("采集模板片段不允许包含模板表达式（{{ }} / {% %}）或双下划线 __")

        child_template_id = CustomSnmpPluginService.get_child_template(plugin).id

        with transaction.atomic():
            child_template = MonitorPluginConfigTemplate.objects.select_for_update().filter(id=child_template_id).first()
            if child_template is None:
                raise BaseAppException("当前 SNMP 模板缺少采集配置")
            original_content = child_template.content

            updated_content = CustomSnmpPluginService._replace_collect_snippet(
                child_template.content,
                normalized_snippet,
            )
            CustomSnmpPluginService._validate_child_template(plugin, child_template, updated_content)
            child_template.content = updated_content
            child_template.save(update_fields=["content", "updated_at"])

        try:
            update_plan = CustomSnmpPluginService._build_propagation_plan(plugin, updated_content, child_template)
            CustomSnmpPluginService.propagate_collect_template(update_plan)
        except Exception:
            MonitorPluginConfigTemplate.objects.filter(id=child_template_id).update(content=original_content)
            raise
        return CustomSnmpPluginService.get_collect_template(plugin)
