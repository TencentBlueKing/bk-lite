import hashlib
import json
import uuid

from django.utils import timezone

from apps.monitor.models import CollectDetectTask, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.services.collect_detect_runtime import (
    build_write_config_and_telegraf_command,
    disable_real_outputs,
    render_telegraf_config_template,
    sanitize_execution_result,
)
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


class CollectDetectService:
    @classmethod
    def create_task(cls, payload: dict, user, organization: int):
        plugin = cls._get_supported_plugin(payload.get("monitor_plugin_id"))
        instance = payload.get("instance") or {}
        env = payload.get("env") or {}
        runtime_payload = {
            "instance": instance,
            "env": env,
            "timeout": int(payload.get("timeout") or 60),
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
            instance = runtime_payload.get("instance") or {}
            config_id = instance.get("config_id") or f"detect_{task.id}"
            env = cls._build_preflight_env(instance, runtime_payload.get("env") or {}, config_id)
            config_context = {
                **instance,
                "config_id": config_id,
                "monitor_plugin_id": plugin.id,
                "collector": plugin.collector,
                "collect_type": plugin.collect_type,
            }
            templates = cls._get_child_templates(plugin, cls._resolve_config_types(instance, plugin))
            config_content = disable_real_outputs(
                "\n\n".join(render_telegraf_config_template(template.content, config_context) for template in templates)
            )
            config_path = f"/tmp/bklite-telegraf-detect-{task.id}-{uuid.uuid4().hex}.toml"
            command = build_write_config_and_telegraf_command(config_path, config_content)

            task.phase = "execute_once"
            task.save(update_fields=["phase", "updated_at"])
            raw_result = Executor(task.node_id).execute_local(
                command,
                timeout=int(runtime_payload.get("timeout") or 60),
                shell="sh",
                env=env,
            )
            result = sanitize_execution_result(raw_result, sensitive_values=list(env.values()))
            task.result = result
            task.status = "success" if result["success"] else "failed"
            task.phase = "parse_output"
            task.error_message = result["stderr"] if not result["success"] else ""
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
    def _get_supported_plugin(plugin_id):
        plugin = MonitorPlugin.objects.filter(id=plugin_id).first()
        if not plugin:
            raise ValueError("监控插件不存在")
        if not plugin.support_collect_detect:
            raise ValueError("当前插件不支持采集检测")
        if plugin.collector != "Telegraf" or plugin.template_type != "builtin":
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
            template = MonitorPluginConfigTemplate.objects.filter(
                plugin=plugin,
                file_type="toml",
            ).order_by("id").first()
        if not template:
            raise ValueError("未找到 Telegraf TOML 采集模板")
        return [template]

    @staticmethod
    def _resolve_config_types(instance, plugin):
        metric_type = instance.get("metric_type")
        if isinstance(metric_type, list):
            return metric_type
        if metric_type:
            return [metric_type]
        return [plugin.collect_type]

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
            env[f"{str(key).upper()}__{config_id}"] = str(value)
        env.update(explicit_env or {})
        return env

    @staticmethod
    def _is_sensitive_key(key):
        key_lower = str(key).lower()
        return any(item in key_lower for item in SENSITIVE_KEYS)

    @classmethod
    def _fingerprint(cls, plugin_id, node_id, instance):
        safe_instance = cls._sanitize_mapping(instance)
        source = json.dumps(
            {"plugin_id": plugin_id, "node_id": node_id, "instance": safe_instance},
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()
