import hashlib
import json
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.models import CollectDetectTask, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.services.collect_detect_runtime import (
    build_telegraf_detect_execution,
    disable_real_outputs,
    render_telegraf_config_template,
    sanitize_execution_result,
    script_isolation_name_prefixes,
    substitute_sidecar_node_variables,
)
from apps.monitor.services.custom_script_plugin import (
    SCRIPT_DETECT_TIMEOUT_MARGIN,
    CustomScriptPluginService,
    assert_script_interval,
    default_script_timeout_seconds,
)
from apps.monitor.services.website_config import normalize_website_request_config
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Node
from apps.node_mgmt.services.package import PackageService
from apps.rpc.executor import Executor

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "token",
    "secret",
    "private_key",
    "private_key_content",
    "passphrase",
    "auth_password",
    "priv_password",
}

DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 600
DEFAULT_TERMINAL_TTL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_CLEANUP_BATCH_SIZE = 500
TERMINAL_STATUSES = ("success", "failed")
# 与正式下发 Controller.render_context 对齐；脚本 child 模板无 default 的变量缺了会渲出空 TOML。
SCRIPT_REQUIRED_RENDER_VARS = ("plugin_id", "instance_id", "instance_type", "config_id", "script", "interval")
# 与前端 run_as 校验一致：root、纯 0、uid=0 / uid:0。
_LINUX_ROOT_RUN_AS_UID = re.compile(r"^(?:0+|uid\s*[:=]\s*0+)$")


class CollectDetectService:
    @classmethod
    def create_task(cls, payload: dict, user, organization: int):
        plugin = cls._get_supported_plugin(payload.get("monitor_plugin_id"))
        instance = payload.get("instance") or {}
        if plugin.collect_type == "web":
            instance = normalize_website_request_config(instance)
        instance = cls._inject_formal_config_vars(plugin, instance)
        try:
            cls._ensure_script_run_as(plugin, instance)
        except ValueError as exc:
            raise ValidationAppException(str(exc)) from exc
        if cls._is_script_plugin(plugin):
            interval_seconds = assert_script_interval(instance.get("interval"))
            instance.pop("timeout", None)
            timeout_seconds = default_script_timeout_seconds(interval_seconds)
            runtime_timeout = timeout_seconds + SCRIPT_DETECT_TIMEOUT_MARGIN
        else:
            runtime_timeout = cls._normalize_timeout(payload.get("timeout"))
        env = payload.get("env") or {}
        runtime_payload = {
            "instance": instance,
            "env": env,
            "timeout": runtime_timeout,
        }

        task = CollectDetectTask.objects.create(
            status="pending",
            phase="validate",
            monitor_plugin_id=plugin.id,
            monitor_object_id=int(payload.get("monitor_object_id") or 0),
            collector=plugin.collector,
            collect_type=plugin.collect_type,
            node_id=str(payload.get("node_id") or ""),
            instance_key=str(payload.get("instance_key") or instance.get("instance_id") or ""),
            request_fingerprint=cls._fingerprint(plugin.id, payload.get("node_id"), instance),
            created_by=getattr(user, "username", "") or "",
            organization=int(organization),
            request_snapshot={
                "monitor_plugin_id": plugin.id,
                "monitor_object_id": payload.get("monitor_object_id"),
                "node_id": payload.get("node_id"),
                "instance_key": payload.get("instance_key"),
                "instance": cls._sanitize_mapping(instance),
                "env": cls._sanitize_mapping(env),
            },
        )
        from apps.monitor.tasks.collect_detect import run_collect_detect_task

        run_collect_detect_task.delay(task.id, runtime_payload)
        return task

    @classmethod
    def run_task(cls, task_id: int, runtime_payload: dict):
        task = CollectDetectTask.objects.get(id=task_id)
        task.status = "running"
        task.phase = "render_config"
        task.started_at = timezone.now()
        task.save(update_fields=["status", "phase", "started_at", "updated_at"])

        try:
            plugin = cls._get_supported_plugin(task.monitor_plugin_id)
            instance = dict(runtime_payload.get("instance") or {})
            if not instance.get("instance_id"):
                fallback_instance_id = task.instance_key or instance.get("instance_name") or instance.get("host")
                if fallback_instance_id:
                    instance["instance_id"] = str(fallback_instance_id)
            config_id = instance.get("config_id") or f"detect_{task.id}"
            node = Node.objects.filter(id=task.node_id).first()
            config_context = cls._inject_formal_config_vars(
                plugin,
                instance,
                config_id=config_id,
                node=node,
            )
            cls._ensure_required_render_vars(plugin, config_context)
            env = cls._build_preflight_env(config_context, runtime_payload.get("env") or {}, config_id)
            if cls._is_script_plugin(plugin):
                config_content = disable_real_outputs(CustomScriptPluginService.render_child_template(config_context))
            else:
                templates = cls._get_child_templates(plugin, cls._resolve_config_types(config_context, plugin))
                config_content = disable_real_outputs(
                    "\n\n".join(render_telegraf_config_template(template.content, config_context) for template in templates)
                )
            config_content = substitute_sidecar_node_variables(config_content, node)
            operating_system, executable_path = cls._resolve_telegraf_runtime(task.node_id)
            config_file_name = f"bklite-telegraf-detect-{task.id}-{uuid.uuid4().hex}.toml"
            command, shell = build_telegraf_detect_execution(
                operating_system=operating_system,
                executable_path=executable_path,
                config_file_name=config_file_name,
                config_content=config_content,
            )

            task.phase = "execute_once"
            task.save(update_fields=["phase", "updated_at"])
            raw_result = Executor(task.node_id).execute_local(
                command,
                timeout=int(runtime_payload.get("timeout") or DEFAULT_TIMEOUT_SECONDS),
                shell=shell,
                env=env,
            )
            result = sanitize_execution_result(raw_result, sensitive_values=list(env.values()))
            if plugin.collect_type == "web" and config_context.get("request_url"):
                result["request_url"] = config_context["request_url"]
            if cls._is_script_plugin(plugin):
                result["isolation_name_prefixes"] = script_isolation_name_prefixes(config_id)
            task.result = result
            task.status = "success" if result["success"] else "failed"
            task.phase = "parse_output"
            task.error_message = "" if result["success"] else (result["stderr"] or result.get("stdout") or "")
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "phase", "result", "error_message", "finished_at", "updated_at"])
            return result
        except Exception as exc:
            safe_message = sanitize_execution_result(
                {"success": False, "error": str(exc)},
                sensitive_values=list((runtime_payload.get("env") or {}).values()),
            )["stderr"]
            task.status = "failed"
            task.error_message = safe_message
            task.result = {"success": False, "stdout": "", "stderr": safe_message, "exit_code": 1}
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "result", "error_message", "finished_at", "updated_at"])
            return task.result

    @staticmethod
    def _resolve_telegraf_runtime(node_id):
        node = Node.objects.filter(id=node_id).first()
        if not node:
            raise ValueError("采集节点不存在")
        if node.operating_system not in {NodeConstants.LINUX_OS, NodeConstants.WINDOWS_OS}:
            raise ValueError(f"不支持的节点操作系统: {node.operating_system}")

        collector = PackageService.resolve_collector_by_architecture(
            node.operating_system,
            "Telegraf",
            node.cpu_architecture,
        )
        if not collector:
            raise ValueError("未找到适用的 Telegraf 采集器")
        return node.operating_system, collector.executable_path

    @staticmethod
    def _get_supported_plugin(plugin_id):
        from apps.monitor.services.ui_template_locale import resolve_support_collect_detect

        plugin = MonitorPlugin.objects.filter(id=plugin_id).prefetch_related("monitor_object").first()
        if not plugin:
            raise ValueError("监控插件不存在")
        if not resolve_support_collect_detect(plugin, fallback=plugin.support_collect_detect):
            raise ValueError("当前插件不支持采集检测")
        if plugin.collector != "Telegraf" or plugin.template_type not in {"builtin", "script"}:
            raise ValueError("当前插件不支持采集检测")
        return plugin

    @staticmethod
    def _get_child_templates(plugin, config_types=None):
        config_types = [item for item in (config_types or []) if item]
        if config_types:
            templates = list(
                MonitorPluginConfigTemplate.objects.filter(
                    plugin=plugin,
                    config_type__in=config_types,
                    file_type="toml",
                ).order_by("id")
            )
            if templates:
                return templates

        template = (
            MonitorPluginConfigTemplate.objects.filter(
                plugin=plugin,
                config_type=plugin.collect_type,
                file_type="toml",
            )
            .order_by("id")
            .first()
        )
        if not template:
            template = (
                MonitorPluginConfigTemplate.objects.filter(
                    plugin=plugin,
                    file_type="toml",
                )
                .order_by("id")
                .first()
            )
        if not template:
            raise ValueError("未找到 Telegraf TOML 采集模板")
        return [template]

    @staticmethod
    def _resolve_config_types(instance, plugin):
        metric_type = instance.get("metric_type")
        if isinstance(metric_type, list):
            config_types = [item for item in metric_type if item]
        elif metric_type:
            config_types = [metric_type]
        else:
            config_types = [plugin.collect_type]
        if plugin.template_type == "script" or plugin.collect_type == "script":
            if "child" not in config_types:
                config_types = [*config_types, "child"]
        return config_types

    @staticmethod
    def _plugin_template_id(plugin):
        return plugin.template_id or plugin.id

    @classmethod
    def _inject_formal_config_vars(cls, plugin, instance, *, config_id=None, node=None):
        """探测渲染与正式采集共用 plugin_id / instance_type 等平台变量。"""
        context = dict(instance or {})
        if not context.get("instance_id"):
            fallback = context.get("instance_name") or context.get("host")
            if fallback:
                context["instance_id"] = str(fallback)
        if not str(context.get("instance_type") or "").strip():
            monitor_object = plugin.monitor_object.all().order_by("id").first()
            if monitor_object is not None:
                context["instance_type"] = monitor_object.name
        if config_id:
            context["config_id"] = config_id
        # 正式下发以平台值为准，覆盖实例里可能带来的空值或伪造 plugin_id。
        context["monitor_plugin_id"] = plugin.id
        context["plugin_id"] = cls._plugin_template_id(plugin)
        context["collector"] = plugin.collector
        context["collect_type"] = plugin.collect_type
        if node is not None and not str(context.get("operating_system") or "").strip():
            context["operating_system"] = node.operating_system
        if plugin.template_type == "script" or plugin.collect_type == "script":
            if not str(context.get("script") or "").strip() and context.get("command") not in (None, ""):
                context["script"] = context["command"]
        return context

    @classmethod
    def _ensure_required_render_vars(cls, plugin, context):
        required = ("plugin_id",)
        if plugin.template_type == "script" or plugin.collect_type == "script":
            required = SCRIPT_REQUIRED_RENDER_VARS
        missing = []
        for key in required:
            value = context.get(key)
            if value is None or (isinstance(value, str) and not str(value).strip()):
                missing.append(key)
                continue
            if key == "interval":
                try:
                    if int(value) <= 0:
                        missing.append(key)
                except (TypeError, ValueError):
                    missing.append(key)
        if missing:
            raise ValueError(f"采集探测缺少必要配置: {', '.join(missing)}")
        cls._ensure_script_run_as(plugin, context)

    @staticmethod
    def _is_script_plugin(plugin) -> bool:
        return plugin.template_type == "script" or plugin.collect_type == "script"

    @classmethod
    def _script_run_as_targets_windows(cls, context) -> bool:
        """与表单一致：显式 script_os 优先；缺省时才看节点操作系统。未知目标按 Linux。"""
        script_os = str((context or {}).get("script_os") or "").strip().lower()
        if script_os == "windows":
            return True
        if script_os == "linux":
            return False
        operating_system = str((context or {}).get("operating_system") or "").strip().lower()
        return operating_system == NodeConstants.WINDOWS_OS

    @classmethod
    def _linux_run_as_forbidden(cls, value: str) -> bool:
        text = value.strip().lower()
        if text == "root":
            return True
        return _LINUX_ROOT_RUN_AS_UID.fullmatch(text) is not None

    @classmethod
    def _ensure_script_run_as(cls, plugin, context):
        """Linux 脚本探测失败关闭：缺 run_as 或 root/UID 0 直接拒绝。Windows 省略该字段。"""
        if not isinstance(context, dict) or not cls._is_script_plugin(plugin):
            return
        if cls._script_run_as_targets_windows(context):
            context.pop("run_as", None)
            return
        raw = context.get("run_as")
        text = "" if raw is None else str(raw).strip()
        if not text:
            raise ValueError("采集探测缺少必要配置: run_as")
        if cls._linux_run_as_forbidden(text):
            raise ValueError("Linux 脚本探测不允许以 root 或 UID 0 运行")

    @classmethod
    def _sanitize_mapping(cls, value):
        if isinstance(value, dict):
            return {key: ("***" if cls._is_sensitive_key(key) else cls._sanitize_mapping(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._sanitize_mapping(item) for item in value]
        return value

    @classmethod
    def _build_preflight_env(cls, instance, explicit_env, config_id):
        env = {}
        for key, value in (instance or {}).items():
            if value in (None, "") or not cls._is_sensitive_key(key):
                continue
            env_key = str(key).upper()
            if env_key.startswith("ENV_"):
                env_key = env_key[4:]
            env[f"{env_key}__{config_id}"] = str(value)
        env.update(explicit_env or {})
        return env

    @staticmethod
    def _is_sensitive_key(key):
        key_lower = str(key).lower()
        return any(item in key_lower for item in SENSITIVE_KEYS)

    @staticmethod
    def _normalize_timeout(timeout):
        try:
            normalized = int(timeout or DEFAULT_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            normalized = DEFAULT_TIMEOUT_SECONDS
        if normalized < 1:
            return DEFAULT_TIMEOUT_SECONDS
        return min(normalized, MAX_TIMEOUT_SECONDS)

    @classmethod
    def _fingerprint(cls, plugin_id, node_id, instance):
        safe_instance = cls._sanitize_mapping(instance)
        source = json.dumps(
            {"plugin_id": plugin_id, "node_id": node_id, "instance": safe_instance},
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @classmethod
    def purge_terminal_tasks(cls, now=None) -> int:
        if not getattr(settings, "COLLECT_DETECT_TASK_CLEANUP_ENABLED", True):
            return 0

        current = now or timezone.now()
        ttl_seconds = int(getattr(settings, "COLLECT_DETECT_TASK_TTL_SECONDS", DEFAULT_TERMINAL_TTL_SECONDS))
        batch_size = int(getattr(settings, "COLLECT_DETECT_TASK_CLEANUP_BATCH_SIZE", DEFAULT_CLEANUP_BATCH_SIZE))
        cutoff = current - timedelta(seconds=ttl_seconds)
        stale_ids = list(
            CollectDetectTask.objects.filter(
                status__in=TERMINAL_STATUSES,
                finished_at__lt=cutoff,
            ).values_list(
                "id", flat=True
            )[:batch_size]
        )
        if not stale_ids:
            return 0
        deleted, _ = CollectDetectTask.objects.filter(id__in=stale_ids).delete()
        return deleted
