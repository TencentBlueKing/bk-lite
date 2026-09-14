"""Preview/apply collector release packs into package slots and monitor plugins."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import node_logger as logger
from apps.monitor.models import MonitorPlugin
from apps.monitor.services.collector_release_plugin import CollectorReleasePluginService
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.models.node_version import NodeComponentVersion
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.services.collector_release.constants import CollectorReleaseConstants as C
from apps.node_mgmt.services.collector_release.errors import (
    ARTIFACT_SLOT_MISSING,
    BINARY_OVERWRITE,
    BINARY_UNCHANGED,
    COLLECTOR_UNKNOWN,
    CONFIRM_REQUIRED,
    IMPORT_LOCKED,
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_WARNING,
    PLUGIN_DOWNGRADE,
    PLUGIN_IMPORT_FAILED,
    PLUGIN_OVERWRITE,
    PREVIEW_EXPIRED,
    STORAGE_FAILED,
    PackIssue,
    issue,
)
from apps.node_mgmt.services.collector_release.guard import guard_pack
from apps.node_mgmt.services.collector_release.pack import ParsedPack, parse_release_path, parse_release_zip
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.utils.version_utils import VersionUtils


class CollectorReleaseService:
    @staticmethod
    def preview_upload(uploaded_file) -> dict:
        uploaded_file.seek(0)
        payload = uploaded_file.read()
        issues, parsed = parse_release_zip(io.BytesIO(payload), compressed_size=len(payload))
        return CollectorReleaseService._build_preview(issues, parsed, payload)

    @staticmethod
    def _build_preview(issues: list[PackIssue], parsed: ParsedPack | None, uploaded_file) -> dict:
        extra: list[PackIssue] = []
        keep_local_slots = set()
        allowlist = {}
        if parsed:
            extra, meta = CollectorReleaseService._collect_runtime_issues(parsed)
            keep_local_slots = meta.get("keep_local_slots") or set()
            allowlist = meta.get("allowlist") or {}
        all_issues = [item.to_dict() for item in issues + extra]
        has_errors = any(item["level"] == LEVEL_ERROR for item in all_issues)
        token = ""
        if parsed and not has_errors:
            token = CollectorReleaseService._stage_bytes(uploaded_file, parsed)
        summary = CollectorReleaseService._pack_summary(parsed) if parsed else None
        if summary is not None:
            summary["allowlist"] = {
                "flags": sorted(allowlist.get("flags") or []),
                "form_fields": sorted(allowlist.get("form_fields") or []),
            }
        return {
            "token": token,
            "has_errors": has_errors,
            "issues": all_issues,
            "requires_confirm": sorted({item["code"] for item in all_issues if item["level"] == LEVEL_WARNING}),
            "keep_local_slots": list(keep_local_slots),
            "pack": summary,
        }

    @staticmethod
    def _collect_runtime_issues(parsed: ParsedPack) -> tuple[list[PackIssue], dict]:
        issues: list[PackIssue] = []
        collectors = list(Collector.objects.filter(name=parsed.collector))
        if not collectors:
            issues.append(
                issue(
                    COLLECTOR_UNKNOWN,
                    f"采集器 {parsed.collector} 在本环境不存在，不能从 zip 新建。",
                    details={"collector": parsed.collector},
                )
            )
            return issues, {}

        for artifact in parsed.artifacts:
            slot = next(
                (item for item in collectors if item.node_operating_system == artifact.os and item.cpu_architecture == artifact.arch),
                None,
            )
            if not slot:
                issues.append(
                    issue(
                        ARTIFACT_SLOT_MISSING,
                        f"没有 {parsed.collector} 的 {artifact.os}/{artifact.arch} 采集器槽位，无法导入该架构。",
                        hint="请从包中去掉该架构，或升级包含对应槽位的版本。",
                        details={"collector": parsed.collector, "os": artifact.os, "arch": artifact.arch},
                    )
                )
                continue
            existing = PackageVersion.objects.filter(
                os=artifact.os,
                cpu_architecture=artifact.arch,
                object=parsed.collector,
                version=parsed.version,
            ).first()
            if existing and existing.sha256 and existing.sha256 == artifact.computed_sha256:
                issues.append(
                    issue(
                        BINARY_UNCHANGED,
                        f"{artifact.os}/{artifact.arch} 与库内 {parsed.version} 哈希相同，将跳过上传。",
                        details={"os": artifact.os, "arch": artifact.arch, "version": parsed.version},
                        level=LEVEL_INFO,
                    )
                )
            elif existing:
                issues.append(
                    issue(
                        BINARY_OVERWRITE,
                        f"{artifact.os}/{artifact.arch} 版本 {parsed.version} 哈希不同，确认后将覆盖。",
                        details={"os": artifact.os, "arch": artifact.arch, "version": parsed.version},
                        level=LEVEL_WARNING,
                    )
                )

        present = {(item.os, item.arch) for item in parsed.artifacts}
        missing_in_pack = []
        for slot in collectors:
            key = (slot.node_operating_system, slot.cpu_architecture)
            if key not in present:
                latest = (
                    PackageVersion.objects.filter(
                        object=parsed.collector,
                        os=slot.node_operating_system,
                        cpu_architecture=slot.cpu_architecture,
                    )
                    .order_by("-id")
                    .first()
                )
                missing_in_pack.append(
                    {
                        "os": slot.node_operating_system,
                        "arch": slot.cpu_architecture,
                        "kept_version": latest.version if latest else "",
                    }
                )
        if missing_in_pack:
            issues.append(
                issue(
                    BINARY_UNCHANGED,
                    "本包未包含的操作系统/架构仍保留库内旧包，可能出现跨架构版本不一致。",
                    details={"kept": missing_in_pack},
                    level=LEVEL_INFO,
                )
            )

        guard_issues, guard_meta = guard_pack(parsed)
        issues.extend(guard_issues)

        fingerprint = CollectorReleasePluginService.current_plugin_fingerprint(parsed.collector)
        current_version = fingerprint.get("pack_version") or ""
        plugin_changed = CollectorReleaseService._plugin_content_changed(parsed, fingerprint)
        skip_plugin = bool(current_version) and current_version == parsed.version and not plugin_changed
        if current_version and current_version != parsed.version:
            if VersionUtils.parse_version(parsed.version) < VersionUtils.parse_version(current_version):
                issues.append(
                    issue(
                        PLUGIN_DOWNGRADE,
                        f"包版本 {parsed.version} 低于当前插件 {current_version}，确认后才更新插件。",
                        details={"current": current_version, "incoming": parsed.version},
                        level=LEVEL_WARNING,
                    )
                )
            else:
                issues.append(
                    issue(
                        PLUGIN_OVERWRITE,
                        f"将用 {parsed.version} 覆盖当前插件 {current_version}。",
                        details={"current": current_version, "incoming": parsed.version},
                        level=LEVEL_WARNING,
                    )
                )
        elif current_version == parsed.version and plugin_changed:
            issues.append(
                issue(
                    PLUGIN_OVERWRITE,
                    f"同版本插件内容有变化，确认后将覆盖（{parsed.version}）。",
                    details={"version": parsed.version},
                    level=LEVEL_WARNING,
                )
            )
        guard_meta["skip_plugin"] = skip_plugin
        return issues, guard_meta

    @staticmethod
    def _plugin_content_changed(parsed: ParsedPack, fingerprint: dict) -> bool:
        if not fingerprint.get("exists"):
            return True
        templates = []
        for item in (parsed.child_template, parsed.base_template):
            if not item:
                continue
            templates.append(
                {
                    "type": item.type,
                    "config_type": item.config_type,
                    "file_type": item.file_type,
                    "content": item.content,
                }
            )
        incoming = CollectorReleasePluginService.content_sha256(parsed.metrics, parsed.ui, templates)
        current = fingerprint.get("pack_content_sha256") or ""
        if current:
            return incoming != current
        incoming_ui = json.dumps(parsed.ui or {}, sort_keys=True, default=str)
        current_ui = json.dumps(fingerprint.get("ui") or {}, sort_keys=True, default=str)
        if incoming_ui != current_ui:
            return True
        current_templates = fingerprint.get("templates") or []

        def _key(row):
            return (row.get("type"), row.get("config_type"), row.get("file_type"), row.get("content"))

        return sorted(map(_key, templates)) != sorted(map(_key, current_templates))

    @staticmethod
    def _pack_summary(parsed: ParsedPack) -> dict:
        return {
            "collector": parsed.collector,
            "collect_type": parsed.collect_type,
            "version": parsed.version,
            "execute_parameters": parsed.execute_parameters,
            "hashes": {
                "metrics": parsed.metrics_sha256,
                "ui": parsed.ui_sha256,
            },
            "artifacts": [
                {
                    "os": item.os,
                    "arch": item.arch,
                    "file": item.file,
                    "sha256": item.computed_sha256,
                    "size": item.size,
                }
                for item in parsed.artifacts
            ],
        }

    @staticmethod
    def _stage_bytes(payload: bytes, parsed: ParsedPack) -> str:
        token = uuid.uuid4().hex
        staging_dir = tempfile.mkdtemp(prefix="collector_release_")
        zip_path = os.path.join(staging_dir, "pack.zip")
        Path(zip_path).write_bytes(payload)
        cache.set(
            f"{C.STAGING_CACHE_PREFIX}{token}",
            {"path": zip_path, "collector": parsed.collector, "version": parsed.version},
            C.PREVIEW_TTL_SECONDS,
        )
        return token

    @staticmethod
    def apply(token: str, confirms: list[str] | None = None) -> dict:
        confirms = set(confirms or [])
        staged = cache.get(f"{C.STAGING_CACHE_PREFIX}{token}")
        if not staged:
            raise ValidationAppException("预览已过期，请重新选择文件预览。", data={"code": PREVIEW_EXPIRED})

        lock_key = f"{C.LOCK_CACHE_PREFIX}{staged['collector']}"
        if not cache.add(lock_key, token, C.LOCK_TTL_SECONDS):
            raise ValidationAppException("同一采集器正在导入，请稍后重试。", data={"code": IMPORT_LOCKED})

        uploaded_keys = []
        cleanup_staging = False
        try:
            issues, parsed = parse_release_path(staged["path"])
            extra, meta = ([], {})
            if parsed:
                extra, meta = CollectorReleaseService._collect_runtime_issues(parsed)
            all_issues = issues + extra
            errors = [item for item in all_issues if item.level == LEVEL_ERROR]
            if errors:
                return {"ok": False, "issues": [item.to_dict() for item in all_issues]}

            warnings = [item.code for item in all_issues if item.level == LEVEL_WARNING]
            missing = sorted(set(warnings) - confirms)
            if missing:
                return {
                    "ok": False,
                    "issues": [
                        issue(
                            CONFIRM_REQUIRED,
                            f"请确认后再导入: {', '.join(missing)}。",
                            details={"required": missing},
                        ).to_dict()
                    ]
                    + [item.to_dict() for item in all_issues],
                }

            keep_local_slots = meta.get("keep_local_slots") or set()
            artifact_results = []
            with transaction.atomic():
                for artifact in parsed.artifacts:
                    collector = Collector.objects.get(
                        name=parsed.collector,
                        node_operating_system=artifact.os,
                        cpu_architecture=artifact.arch,
                    )
                    executable_name = os.path.basename(collector.executable_path.replace("\\", "/"))
                    existing = PackageVersion.objects.filter(
                        os=artifact.os,
                        cpu_architecture=artifact.arch,
                        object=parsed.collector,
                        version=parsed.version,
                    ).first()
                    action = "created"
                    if existing and existing.sha256 == artifact.computed_sha256:
                        action = "skipped"
                    else:
                        payload = parsed.files[artifact.file]
                        content = ContentFile(payload, name=executable_name)
                        data = {
                            "os": artifact.os,
                            "cpu_architecture": artifact.arch,
                            "object": parsed.collector,
                            "version": parsed.version,
                            "name": executable_name,
                        }
                        try:
                            PackageService.upload_file(content, data)
                            uploaded_keys.append(f"{artifact.os}/{artifact.arch}/{parsed.collector}/{parsed.version}/{executable_name}")
                        except Exception as exc:
                            logger.exception("collector release storage upload failed")
                            raise ValidationAppException(
                                "对象存储写入失败，已回滚库表。",
                                data={"code": STORAGE_FAILED},
                            ) from exc
                        if existing:
                            existing.name = executable_name
                            existing.sha256 = artifact.computed_sha256
                            existing.type = PackageConstants.TYPE_COLLECTOR
                            existing.save(update_fields=["name", "sha256", "type"])
                            action = "overwritten"
                        else:
                            PackageVersion.objects.create(
                                type=PackageConstants.TYPE_COLLECTOR,
                                os=artifact.os,
                                cpu_architecture=artifact.arch,
                                object=parsed.collector,
                                version=parsed.version,
                                name=executable_name,
                                sha256=artifact.computed_sha256,
                            )
                            action = "created"
                    if collector.id not in keep_local_slots and parsed.execute_parameters:
                        collector.execute_parameters = parsed.execute_parameters
                    collector.imported_package_version = parsed.version
                    collector.save(update_fields=["execute_parameters", "imported_package_version"])
                    artifact_results.append({"os": artifact.os, "arch": artifact.arch, "action": action})

                templates = []
                if parsed.child_template:
                    templates.append(parsed.child_template.__dict__)
                if parsed.base_template:
                    templates.append(parsed.base_template.__dict__)
                if not meta.get("skip_plugin"):
                    try:
                        CollectorReleasePluginService.import_from_pack(
                            {
                                "metrics": parsed.metrics,
                                "ui": parsed.ui,
                                "templates": templates,
                                "collector": parsed.collector,
                                "collect_type": parsed.collect_type,
                                "version": parsed.version,
                            }
                        )
                    except Exception as exc:
                        logger.exception("collector release plugin import failed")
                        raise ValidationAppException(
                            "监控插件写入失败，二进制未生效。",
                            data={"code": PLUGIN_IMPORT_FAILED},
                        ) from exc

            CollectorReleaseService.refresh_collector_upgrade_hints(parsed.collector)
            cache.delete(f"{C.STAGING_CACHE_PREFIX}{token}")
            cleanup_staging = True
            plugin_name = ""
            if isinstance(parsed.metrics, dict):
                plugin_name = str(parsed.metrics.get("plugin") or "").strip()
            return {
                "ok": True,
                "collector": parsed.collector,
                "version": parsed.version,
                "artifacts": artifact_results,
                "issues": [item.to_dict() for item in all_issues if item.level != LEVEL_ERROR],
                "monitor_object_id": CollectorReleasePluginService.resolve_entry_monitor_object_id(
                    plugin_name=plugin_name or parsed.collector,
                    collector=parsed.collector,
                ),
                "message": "导入成功。已接入实例不会自动重下发，须到接入页再保存；节点二进制须再安装或升级。",
            }
        except Exception:
            for key in uploaded_keys:
                try:
                    parts = key.split("/")
                    PackageService.delete_file(
                        SimpleNamespace(
                            os=parts[0],
                            cpu_architecture=parts[1],
                            object=parts[2],
                            version=parts[3],
                            name=parts[4],
                        )
                    )
                except Exception:
                    logger.exception("failed to compensate uploaded collector release object")
            raise
        finally:
            cache.delete(lock_key)
            if cleanup_staging:
                path = staged.get("path")
                if path:
                    shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    @staticmethod
    def restore_builtin(collector_name: str) -> dict:
        from apps.node_mgmt.services.collector_release.allowlist import load_builtin_collectors

        plugin_result = CollectorReleasePluginService.restore_builtin(collector_name)
        builtins = {(item.get("node_operating_system"), item.get("cpu_architecture")): item for item in load_builtin_collectors(collector_name)}
        for collector in Collector.objects.filter(name=collector_name):
            builtin = builtins.get((collector.node_operating_system, collector.cpu_architecture))
            if builtin and builtin.get("execute_parameters") is not None:
                collector.execute_parameters = builtin["execute_parameters"]
            collector.imported_package_version = ""
            collector.save(update_fields=["execute_parameters", "imported_package_version"])
        return {"collector": collector_name, "plugin": plugin_result}

    @staticmethod
    def refresh_collector_upgrade_hints(collector_name: str) -> None:
        latest_map = VersionUpgradeService.get_latest_versions_map("collector")
        for record in NodeComponentVersion.objects.filter(component_type="collector"):
            collector = Collector.objects.filter(id=record.component_id).first()
            if not collector or collector.name != collector_name:
                continue
            latest = ((latest_map.get(collector.node_operating_system) or {}).get(collector.name) or {}).get(collector.cpu_architecture or "", "")
            record.latest_version = latest
            record.upgradeable = VersionUtils.is_upgradeable(record.version, latest)
            record.save(update_fields=["latest_version", "upgradeable"])

    @staticmethod
    def annotate_collectors(results: list[dict]) -> list[dict]:
        names = {item.get("name") for item in results if item.get("name")}
        packages = PackageVersion.objects.filter(object__in=names, type=PackageConstants.TYPE_COLLECTOR)
        latest = {}
        covered = {}
        for pkg in packages:
            key = (pkg.object, pkg.os, pkg.cpu_architecture)
            covered.setdefault(pkg.object, set()).add(f"{pkg.os}/{pkg.cpu_architecture}")
            current = latest.get(key)
            if not current or VersionUtils.parse_version(pkg.version) > VersionUtils.parse_version(current):
                latest[key] = pkg.version
        plugins = {item.name: item.pack_version for item in MonitorPlugin.objects.filter(name__in=names)}
        for item in results:
            key = (item.get("name"), item.get("node_operating_system"), item.get("cpu_architecture"))
            item["latest_package_version"] = latest.get(key, "")
            item["covered_architectures"] = sorted(covered.get(item.get("name"), set()))
            item["pack_version"] = plugins.get(item.get("name"), "")
        return results
