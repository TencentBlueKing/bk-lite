"""Import a collector-release plugin payload into monitor DB."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.management.services.plugin_migrate import (
    TEMPLATE_COLLECT_TYPE_PATTERN,
    _batch_save_templates,
    _collect_templates_to_process,
    _import_plugins_from_files,
    _load_plugins_to_memory,
    _load_templates_to_memory,
)
from apps.monitor.management.utils import find_files_by_pattern
from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.plugin_guide import PluginGuideService
from apps.monitor.services.ui_template_locale import clear_ui_file_overlay_cache


def _inject_collect_type(content: str, collect_type: str) -> str:
    if not content:
        return content
    return TEMPLATE_COLLECT_TYPE_PATTERN.sub(lambda _match: f'collect_type = "{collect_type}"', content)


class CollectorReleasePluginService:
    @staticmethod
    def content_sha256(metrics: dict | None, ui: dict | None, templates: list | None) -> str:
        payload = {
            "metrics": metrics or {},
            "ui": ui or {},
            "templates": [
                {
                    "type": item.get("type"),
                    "config_type": item.get("config_type"),
                    "file_type": item.get("file_type"),
                    "content": item.get("content"),
                }
                for item in (templates or [])
                if isinstance(item, dict)
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    @staticmethod
    def plugin_has_pack_version(plugin_name: str) -> bool:
        plugin = MonitorPlugin.objects.filter(name=plugin_name).only("pack_version").first()
        return bool(plugin and plugin.pack_version)

    @staticmethod
    def resolve_entry_monitor_object_id(*, plugin_name: str = "", collector: str = "") -> int | None:
        """Resolve the integration-list object id for a just-imported collector pack."""
        plugin = None
        names = [value for value in (plugin_name, collector) if value]
        for name in names:
            plugin = MonitorPlugin.objects.filter(name=name).first()
            if plugin is not None:
                break
        if plugin is None and collector:
            plugin = MonitorPlugin.objects.filter(collector=collector).order_by("id").first()
        if plugin is None:
            return None
        from apps.monitor.serializers.plugin import MonitorPluginSerializer

        parent = MonitorPluginSerializer.get_parent_monitor_object_instance(plugin)
        return parent.id if parent is not None else None

    @staticmethod
    def import_from_pack(payload: dict) -> dict:
        metrics = dict(payload.get("metrics") or {})
        ui = payload.get("ui") or {}
        collect_type = payload.get("collect_type") or metrics.get("collect_type") or ""
        version = payload.get("version") or ""
        collector = payload.get("collector") or metrics.get("collector") or ""
        metrics["collector"] = collector
        metrics["collect_type"] = collect_type
        metrics["_mark_objects_builtin"] = True
        plugin_name = str(metrics.get("plugin") or collector or "").strip()
        if not plugin_name:
            raise BaseAppException("metrics.json 缺少 plugin 名称。")
        # import_monitor_plugin 会 pop plugin/metrics，必须先留下身份和哈希快照。
        hash_metrics = dict(metrics)
        hash_metrics.pop("_mark_objects_builtin", None)

        templates = payload.get("templates") or []
        previous_fingerprint = ""
        try:
            with transaction.atomic():
                existing = MonitorPlugin.objects.filter(name=plugin_name).only("pack_content_sha256", "pack_version").first()
                previous_fingerprint = (existing.pack_content_sha256 or "") if existing else ""
                previous_version = (existing.pack_version or "") if existing else ""
                # 导入新包前，把仍匹配旧指纹且未记录版本的配置钉上旧包版本，避免界面把「当前」当成新版本。
                if existing and previous_fingerprint and previous_version:
                    from apps.monitor.models import CollectConfig

                    CollectConfig.objects.filter(
                        monitor_plugin=existing,
                        applied_content_sha256=previous_fingerprint,
                        applied_pack_version="",
                    ).update(applied_pack_version=previous_version)
                MonitorPluginService.import_monitor_plugin(metrics)
                plugin = MonitorPlugin.objects.get(name=plugin_name)
                plugin.pack_version = version
                plugin.pack_content_sha256 = CollectorReleasePluginService.content_sha256(hash_metrics, ui, templates)
                plugin.template_type = "builtin"
                plugin.collector = collector
                plugin.collect_type = collect_type
                plugin.save(
                    update_fields=[
                        "pack_version",
                        "pack_content_sha256",
                        "template_type",
                        "collector",
                        "collect_type",
                    ]
                )

                if ui:
                    MonitorPluginUITemplate.objects.update_or_create(plugin=plugin, defaults={"content": ui})

                for item in templates:
                    content = _inject_collect_type(item.get("content") or "", collect_type)
                    MonitorPluginConfigTemplate.objects.update_or_create(
                        plugin=plugin,
                        type=item.get("type") or "",
                        config_type=item.get("config_type") or "",
                        file_type=item.get("file_type") or "",
                        defaults={"content": content},
                    )
        except Exception as exc:
            logger.exception("collector release plugin import failed")
            raise BaseAppException(str(exc)) from exc

        PluginGuideService.clear_plugin_dir_cache()
        clear_ui_file_overlay_cache()
        return {
            "plugin": plugin_name,
            "pack_version": version,
            "previous_fingerprint": previous_fingerprint,
            "pack_content_sha256": plugin.pack_content_sha256,
        }

    @staticmethod
    def current_plugin_fingerprint(plugin_name: str) -> dict:
        plugin = MonitorPlugin.objects.filter(name=plugin_name).first()
        if not plugin:
            return {"pack_version": "", "exists": False}
        ui = MonitorPluginUITemplate.objects.filter(plugin=plugin).first()
        templates = list(MonitorPluginConfigTemplate.objects.filter(plugin=plugin).values("type", "config_type", "file_type", "content"))
        return {
            "exists": True,
            "pack_version": plugin.pack_version or "",
            "pack_content_sha256": plugin.pack_content_sha256 or "",
            "ui": ui.content if ui else {},
            "templates": templates,
        }

    @staticmethod
    def restore_builtin(plugin_name: str) -> dict:
        path_list = find_files_by_pattern(PluginConstants.DIRECTORY, filename_pattern="metrics.json")
        path_list.extend(find_files_by_pattern(PluginConstants.ENTERPRISE_DIRECTORY, filename_pattern="metrics.json"))
        matched = []
        for file_path in path_list:
            try:
                data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("plugin") == plugin_name:
                matched.append(file_path)
        if not matched:
            raise BaseAppException(f"未找到内置插件 {plugin_name}")

        plugin = MonitorPlugin.objects.filter(name=plugin_name).first()
        previous_fingerprint = (plugin.pack_content_sha256 or "") if plugin else ""
        previous_version = (plugin.pack_version or "") if plugin else ""
        metrics_payload = {}
        try:
            metrics_payload = json.loads(Path(matched[0]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, IndexError):
            metrics_payload = {}
        if plugin:
            if previous_fingerprint and previous_version:
                from apps.monitor.models import CollectConfig

                CollectConfig.objects.filter(
                    monitor_plugin=plugin,
                    applied_content_sha256=previous_fingerprint,
                    applied_pack_version="",
                ).update(applied_pack_version=previous_version)
            plugin.pack_version = ""
            plugin.save(update_fields=["pack_version"])

        _import_plugins_from_files(matched)
        plugins_dict = _load_plugins_to_memory()
        all_config_templates, all_ui_templates = _load_templates_to_memory()
        templates_data = _collect_templates_to_process(matched, plugins_dict, all_config_templates, all_ui_templates)
        _batch_save_templates(templates_data)
        plugin = MonitorPlugin.objects.filter(name=plugin_name).first()
        builtin_fp = ""
        if plugin:
            ui_obj = MonitorPluginUITemplate.objects.filter(plugin=plugin).first()
            templates = list(
                MonitorPluginConfigTemplate.objects.filter(plugin=plugin).values(
                    "type",
                    "config_type",
                    "file_type",
                    "content",
                )
            )
            builtin_fp = CollectorReleasePluginService.content_sha256(
                metrics_payload,
                ui_obj.content if ui_obj else {},
                templates,
            )
            plugin.pack_version = ""
            plugin.pack_content_sha256 = builtin_fp
            plugin.save(update_fields=["pack_version", "pack_content_sha256"])
        PluginGuideService.clear_plugin_dir_cache()
        clear_ui_file_overlay_cache()
        return {
            "plugin": plugin_name,
            "pack_version": "",
            "previous_fingerprint": previous_fingerprint,
            "pack_content_sha256": builtin_fp,
        }
