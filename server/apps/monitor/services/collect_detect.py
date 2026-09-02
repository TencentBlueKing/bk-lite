import hashlib
import json
import uuid

from django.utils import timezone

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.aix_node_exporter import PLUGIN_NAME as HOST_AIX_PLUGIN_NAME
from apps.monitor.models import CollectDetectTask, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.services.aix_node_exporter import AixNodeExporterError, AixNodeExporterService
from apps.monitor.services.collect_detect_runtime import (
    build_telegraf_detect_execution,
    disable_real_outputs,
    render_telegraf_config_template,
    sanitize_execution_result,
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


class CollectDetectService:
    @classmethod
    def create_task(cls, payload: dict, user, organization: int):
        plugin = cls._get_supported_plugin(payload.get("monitor_plugin_id"))
        instance = payload.get("instance") or {}
        if plugin.collect_type == "web":
            instance = normalize_website_request_config(instance)
        env = payload.get("env") or {}
        runtime_payload = {
            "instance": instance,
            "env": env,
            "timeout": cls._normalize_timeout(payload.get("timeout")),
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
            env = cls._build_preflight_env(instance, runtime_payload.get("env") or {}, config_id)
            config_context = {
                **instance,
                "config_id": config_id,
                "monitor_plugin_id": plugin.id,
                "collector": plugin.collector,
                "collect_type": plugin.collect_type,
            }
            config_types = ["aix"] if plugin.name == HOST_AIX_PLUGIN_NAME else cls._resolve_config_types(instance, plugin)
            templates = cls._get_child_templates(plugin, config_types)
            config_content = disable_real_outputs(
                "\n\n".join(render_telegraf_config_template(template.content, config_context) for template in templates)
            )
            operating_system, executable_path = cls._resolve_telegraf_runtime(task.node_id)
            config_file_name = f"bklite-telegraf-detect-{task.id}-{uuid.uuid4().hex}.toml"
            command, shell = build_telegraf_detect_execution(
                operating_system=operating_system,
                executable_path=executable_path,
                config_file_name=config_file_name,
                config_content=config_content,
            )

            stages = []
            if plugin.name == HOST_AIX_PLUGIN_NAME:
                aix_result = cls._run_aix_copy_and_start(task, instance, env, config_id, stages)
                if aix_result is not None:
                    return aix_result

            task.phase = "execute_once"
            task.save(update_fields=["phase", "updated_at"])
            raw_result = Executor(task.node_id).execute_local(
                command,
                timeout=int(runtime_payload.get("timeout") or 60),
                shell=shell,
                env=env,
            )
            result = sanitize_execution_result(raw_result, sensitive_values=list(env.values()))
            if plugin.collect_type == "web" and instance.get("request_url"):
                result["request_url"] = instance["request_url"]
            if plugin.name == HOST_AIX_PLUGIN_NAME:
                result = cls._finalize_aix_scrape_and_metrics(result, stages)
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

    @classmethod
    def _run_aix_copy_and_start(cls, task, instance, env, config_id, stages):
        credentials = AixNodeExporterService.load_credentials(env, config_id, instance)
        host = instance.get("host")
        scrape_port = instance.get("port") or 9100
        sensitive = [value for value in credentials.values() if value not in (None, "")]
        sensitive.extend(list(env.values()))
        try:
            task.phase = "copy"
            task.save(update_fields=["phase", "updated_at"])
            copy_raw = AixNodeExporterService.copy_package(
                node_id=task.node_id,
                host=host,
                username=credentials["username"],
                password=credentials["password"],
                private_key=credentials["private_key"],
                passphrase=credentials["passphrase"],
            )
            copy_result = sanitize_execution_result(copy_raw, sensitive_values=sensitive)
            stages.append({"stage": "copy", "success": copy_result["success"], "exit_code": copy_result["exit_code"]})
            if not copy_result["success"]:
                return cls._fail_aix_stage(task, copy_result, stages, "copy")

            task.phase = "start"
            task.save(update_fields=["phase", "updated_at"])
            start_raw = AixNodeExporterService.start_exporter(
                node_id=task.node_id,
                host=host,
                username=credentials["username"],
                password=credentials["password"],
                private_key=credentials["private_key"],
                passphrase=credentials["passphrase"],
                scrape_port=scrape_port,
                skip_copy=False,
            )
            start_result = sanitize_execution_result(start_raw, sensitive_values=sensitive)
            stages.append({"stage": "start", "success": start_result["success"], "exit_code": start_result["exit_code"]})
            if not start_result["success"]:
                return cls._fail_aix_stage(task, start_result, stages, "start")
        except AixNodeExporterError as exc:
            logger.warning(
                "event=aix_collect_detect_failed task_id=%s failed_stage=%s error_type=%s",
                task.id,
                exc.failed_stage,
                exc.error_type,
            )
            failed = {
                "success": False,
                "stdout": "",
                "stderr": str(exc),
                "exit_code": 1,
            }
            result = sanitize_execution_result(failed, sensitive_values=sensitive)
            stages.append({"stage": exc.failed_stage, "success": False, "exit_code": 1})
            return cls._fail_aix_stage(task, result, stages, exc.failed_stage)
        return None

    @classmethod
    def _finalize_aix_scrape_and_metrics(cls, result, stages):
        scrape_ok = bool(result.get("success"))
        stages.append({"stage": "scrape", "success": scrape_ok, "exit_code": result.get("exit_code")})
        if not scrape_ok:
            result["stages"] = stages
            result["stage"] = "scrape"
            return result
        stdout = result.get("stdout") or ""
        metrics_ok = any(token in stdout for token in ("node_cpu", "node_memory", "node_load", "node_partition"))
        stages.append({"stage": "metrics", "success": metrics_ok, "exit_code": 0 if metrics_ok else 1})
        result["stages"] = stages
        result["stage"] = "metrics"
        if not metrics_ok:
            result["success"] = False
            result["exit_code"] = 1
            result["stderr"] = result.get("stderr") or "aix metrics missing"
        return result

    @classmethod
    def _fail_aix_stage(cls, task, result, stages, stage):
        result = {**result, "stage": stage, "stages": stages, "success": False}
        if result.get("exit_code") in (None, 0):
            result["exit_code"] = 1
        task.result = result
        task.status = "failed"
        task.phase = stage
        task.error_message = result.get("stderr") or result.get("stdout") or ""
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "phase", "result", "error_message", "finished_at", "updated_at"])
        return result

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

        plugin = MonitorPlugin.objects.filter(id=plugin_id).first()
        if not plugin:
            raise ValueError("监控插件不存在")
        if not resolve_support_collect_detect(plugin, fallback=plugin.support_collect_detect):
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
