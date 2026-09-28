"""Preview/apply collector release packs into package slots and monitor plugins."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from django.core.cache import cache
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
    REGISTER_FAILED,
    STORAGE_FAILED,
    PackIssue,
    issue,
)
from apps.node_mgmt.services.collector_release.guard import guard_pack
from apps.node_mgmt.services.collector_release.pack import ParsedPack, parse_release_path, parse_release_zip
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.utils.version_utils import VersionUtils


class _NamedZipStream(io.BufferedIOBase):
    """给 zipfile 流式句柄补一个 `.name`，让 upload_file_to_s3 的对象存储描述字段
    仍然是可执行文件名（如 kafka_exporter），而不是 zip 内部的成员路径。

    必须真正继承 `io.BufferedIOBase`（而不是随便鸭子类型一个对象）：NATS 的
    object store 客户端专门用 `isinstance(data, io.BufferedIOBase)` 判断是否
    走线程化的 `readinto` 流式上传路径，普通对象会被直接拒绝
    （`TypeError: nats: invalid type for object store`，这个坑在本地联调真实
    NATS 时才会暴露，纯 mock 单测测不出来——已经在下面的手工联调记录里踩过）。
    """

    def __init__(self, stream, name: str):
        super().__init__()
        self._stream = stream
        self.name = name

    def readable(self):
        return True

    def read(self, size=-1, /):
        return self._stream.read(size)

    def readinto(self, b):
        return self._stream.readinto(b)

    def seekable(self):
        return self._stream.seekable()

    def seek(self, offset, whence=0, /):
        return self._stream.seek(offset, whence)

    def tell(self):
        return self._stream.tell()

    def close(self):
        # 真正的关闭由外层 `with zf.open(...) as stream:` 负责；这里只是包了
        # 一层名字，不应该在这一层就把底层的 zip 成员流关掉。
        pass


class CollectorReleaseService:
    @staticmethod
    def preview_upload(uploaded_file) -> dict:
        CollectorReleaseService.sweep_stale_staging()
        uploaded_file.seek(0)
        # 不再 uploaded_file.read() 整包进内存：Django 对 >2.5MB 的上传本来就已经落
        # 盘成临时文件，这里直接把该文件对象交给 zipfile（它只按需 seek/read 具体
        # 成员），避免额外复制出一份最大 200MB 的 bytes（F1，见下面 _stage_bytes
        # 同理）。uploaded_file 本身实现了 read/seek，zipfile 可以直接使用。
        compressed_size = getattr(uploaded_file, "size", None)
        issues, parsed = parse_release_zip(uploaded_file, compressed_size=compressed_size)
        return CollectorReleaseService._build_preview(issues, parsed, uploaded_file)

    @staticmethod
    def sweep_stale_staging(max_age_seconds: int | None = None, *, force: bool = False) -> int:
        """回收超过预览有效期仍残留的暂存目录。

        预览会把整包落到临时目录，只有导入成功才会清理；用户预览后关页面、
        换包或直接不导入时目录会一直留着，因此每次预览前顺手回收一次。

        这里做了节流：实际的文件系统扫描（glob + 逐个 stat）每
        `STAGING_SWEEP_THROTTLE_SECONDS` 最多跑一次，不会随预览请求量线性增长——
        否则请求量越大、/tmp 下残留目录越多，这个「顺手」的清理反而会变成拖慢每次
        预览的热路径开销（F4）。用 cache.add 做节流是因为本仓库对新增 Celery Beat
        周期任务有一套所有权指纹核对流程（见 DEVELOP.md），为一次性的清理任务走
        完整流程成本明显大于收益；真正需要独立调度、可观测的清理时，再迁移成
        Beat 任务不迟。
        """
        if not force and not cache.add(C.STAGING_SWEEP_THROTTLE_CACHE_KEY, 1, C.STAGING_SWEEP_THROTTLE_SECONDS):
            return 0
        max_age = max_age_seconds if max_age_seconds is not None else C.PREVIEW_TTL_SECONDS + C.STAGING_SWEEP_GRACE_SECONDS
        now = time.time()
        removed = 0
        try:
            entries = list(Path(tempfile.gettempdir()).glob(f"{C.STAGING_DIR_PREFIX}*"))
        except OSError:
            logger.exception("failed to scan collector release staging root")
            return 0
        for entry in entries:
            try:
                if not entry.is_dir() or now - entry.stat().st_mtime < max_age:
                    continue
            except OSError:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        if removed:
            logger.info("collector release staging swept: removed=%s max_age=%s", removed, max_age)
        return removed

    @staticmethod
    def discard_staging(token: str) -> dict:
        """用户放弃本次预览时立即释放暂存包，不必等回收窗口。"""
        staged = cache.get(f"{C.STAGING_CACHE_PREFIX}{token}")
        cache.delete(f"{C.STAGING_CACHE_PREFIX}{token}")
        path = (staged or {}).get("path")
        if path:
            shutil.rmtree(os.path.dirname(path), ignore_errors=True)
        return {"discarded": bool(path)}

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
            token = CollectorReleaseService._stage_upload(uploaded_file, parsed)
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
                        f"{artifact.os}/{artifact.arch} 同版本 {parsed.version} 的节点安装包哈希不同，确认后将替换该架构安装包。",
                        hint="只替换组件库里的节点二进制，不会改已有采集任务或已下发配置。",
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
                        f"包版本 {parsed.version} 低于库中当前监控插件 {current_version}，确认后才替换插件定义。",
                        hint=("替换的是监控插件定义（指标、接入表单与配置模板），" "不是采集任务。已接入实例不会自动重下发；" "若配置需更新，请到接入资产页确认。" "目录只保留当前一份，要退回请再导入上一份 zip，不要用「恢复内置」撤销这次导入。"),
                        details={"current": current_version, "incoming": parsed.version},
                        level=LEVEL_WARNING,
                    )
                )
            else:
                issues.append(
                    issue(
                        PLUGIN_OVERWRITE,
                        f"将用包内监控插件 {parsed.version} 替换库中当前插件定义 {current_version}（指标、接入表单与配置模板）。",
                        hint=("不会自动改写或重下发已有采集任务；" "导入后若配置需更新，请到接入资产页确认。" "目录只保留当前一份，要退回请再导入上一份 zip，不要用「恢复内置」撤销这次导入。"),
                        details={"current": current_version, "incoming": parsed.version},
                        level=LEVEL_WARNING,
                    )
                )
        elif current_version == parsed.version and plugin_changed:
            issues.append(
                issue(
                    PLUGIN_OVERWRITE,
                    f"同版本监控插件内容有变化，确认后将用包内定义替换库中插件（指标、接入表单与配置模板，版本 {parsed.version}）。",
                    hint=("不会自动改写或重下发已有采集任务；" "导入后若配置需更新，请到接入资产页确认。" "目录只保留当前一份，要退回请再导入上一份 zip，不要用「恢复内置」撤销这次导入。"),
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
    def _stage_upload(uploaded_file, parsed: ParsedPack) -> str:
        """把上传流拷到暂存目录供 apply() 复用，全程不整包读进内存（F1）。"""
        token = uuid.uuid4().hex
        staging_dir = tempfile.mkdtemp(prefix=C.STAGING_DIR_PREFIX)
        zip_path = os.path.join(staging_dir, "pack.zip")
        uploaded_file.seek(0)
        with open(zip_path, "wb") as dest:
            shutil.copyfileobj(uploaded_file, dest, length=1024 * 1024)
        cache.set(
            f"{C.STAGING_CACHE_PREFIX}{token}",
            {"path": zip_path, "collector": parsed.collector, "version": parsed.version},
            C.PREVIEW_TTL_SECONDS,
        )
        return token

    @staticmethod
    def _import_plugin_payload(parsed: ParsedPack, meta: dict) -> dict:
        if meta.get("skip_plugin"):
            plugin_name = ""
            if isinstance(parsed.metrics, dict):
                plugin_name = str(parsed.metrics.get("plugin") or "").strip()
            plugin = MonitorPlugin.objects.filter(name=plugin_name or parsed.collector).first()
            current = (plugin.pack_content_sha256 or "") if plugin else ""
            return {
                "plugin": (plugin.name if plugin else plugin_name) or parsed.collector,
                "previous_fingerprint": current,
                "pack_content_sha256": current,
            }
        templates = []
        if parsed.child_template:
            templates.append(parsed.child_template.__dict__)
        if parsed.base_template:
            templates.append(parsed.base_template.__dict__)
        try:
            result = CollectorReleasePluginService.import_from_pack(
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
                "监控插件写入失败，已成功的架构二进制保持导入状态。",
                data={"code": PLUGIN_IMPORT_FAILED},
            ) from exc
        return result

    @staticmethod
    def _is_package_registration_error(exc: Exception) -> bool:
        """upload_file 里 staging 上传成功后的库表登记失败，不应再报成对象存储写入失败。"""
        from django.db import DatabaseError, IntegrityError

        return isinstance(exc, (KeyError, IntegrityError, DatabaseError))

    @staticmethod
    def _upload_one_artifact(
        parsed: ParsedPack,
        artifact,
        data: dict,
        executable_name: str,
        existing_package=None,
    ) -> PackageVersion:
        """从暂存 zip 直接流式打开对应成员上传，不把整个二进制读成一份 bytes（F1）。

        返回 upload_file 落好的 PackageVersion。覆盖导入必须传入 existing_package，
        否则 _reserve_pending 会因 unique_together 抛 IntegrityError。
        """
        arcname = f"{parsed.wrapping_prefix}{artifact.file}"
        try:
            with zipfile.ZipFile(parsed.source_path) as zf, zf.open(arcname) as stream:
                return PackageService.upload_file(
                    _NamedZipStream(stream, executable_name),
                    data,
                    existing_package=existing_package,
                )
        except ValidationAppException:
            raise
        except Exception as exc:
            logger.exception(
                "collector release artifact upload failed: os=%s arch=%s",
                artifact.os,
                artifact.arch,
            )
            if CollectorReleaseService._is_package_registration_error(exc):
                raise ValidationAppException(
                    f"{artifact.os}/{artifact.arch} 版本登记失败。",
                    data={"code": REGISTER_FAILED, "os": artifact.os, "arch": artifact.arch},
                ) from exc
            raise ValidationAppException(
                f"{artifact.os}/{artifact.arch} 对象存储写入失败。",
                data={"code": STORAGE_FAILED, "os": artifact.os, "arch": artifact.arch},
            ) from exc

    @staticmethod
    def _commit_one_artifact(parsed: ParsedPack, artifact, keep_local_slots: set) -> dict:
        """单个架构「先传对象存储、传成功再落这一个架构的库表」。

        不再把所有架构的库表写入和上传塞进同一个大事务（F2）：
          1）JetStream 单次 put 超时 120s，四个架构顺序上传最坏能拖到 8 分钟；
             之前的写法会让 Collector/PackageVersion 的行锁、DB 连接占用整个
             上传窗口。导入锁本身按架构续期，不再指望 300s TTL 罩住整段上传；
          2）多架构之间本来就没有真正的跨对象事务——覆盖写一旦发生就不可逆
             （H1 已经证明"先写库表、失败再整体回滚"在覆盖场景下并不可靠）。
             现在按架构逐个提交：只要上传没成功，就完全不碰这个架构的
             PackageVersion/Collector 行，天然不需要任何"失败后再删/再改"的
             补偿逻辑——DB 里出现的每一行，一定对应存储里真实存在的字节。
          3）一个架构上传失败不影响其它架构：已成功的保持已导入状态，运维只需
             针对失败的架构重新导入同一个包（BINARY_UNCHANGED 会让已成功的架构
             自动跳过重传）。
        """
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
        action = "skipped"
        package = existing
        if not (existing and existing.sha256 == artifact.computed_sha256):
            data = {
                "os": artifact.os,
                "cpu_architecture": artifact.arch,
                "object": parsed.collector,
                "version": parsed.version,
                "name": executable_name,
                "type": PackageConstants.TYPE_COLLECTOR,
                "sha256": artifact.computed_sha256,
            }
            # upload_file 会创建或把 existing 置为 READY；此处不再二次 create，避免 unique_together 冲突。
            package = CollectorReleaseService._upload_one_artifact(
                parsed,
                artifact,
                data,
                executable_name,
                existing_package=existing,
            )
            action = "overwritten" if existing else "created"

        with transaction.atomic():
            if action in ("overwritten", "created") and package is not None:
                # 覆盖路径下 upload_file 不会改 sha256/name/type，这里补齐；创建路径则幂等写回。
                package.name = executable_name
                package.sha256 = artifact.computed_sha256
                package.type = PackageConstants.TYPE_COLLECTOR
                package.save(update_fields=["name", "sha256", "type"])
            if collector.id not in keep_local_slots and parsed.execute_parameters:
                collector.execute_parameters = parsed.execute_parameters
            collector.imported_package_version = parsed.version
            collector.save(update_fields=["execute_parameters", "imported_package_version"])
        return {"os": artifact.os, "arch": artifact.arch, "action": action}

    @staticmethod
    def apply(token: str, confirms: list[str] | None = None, actor_context=None) -> dict:
        confirms = set(confirms or [])
        staged = cache.get(f"{C.STAGING_CACHE_PREFIX}{token}")
        if not staged:
            raise ValidationAppException("预览已过期，请重新选择文件预览。", data={"code": PREVIEW_EXPIRED})

        collector_name = staged["collector"]
        CollectorReleaseService._acquire_import_lock(collector_name, token)

        cleanup_staging = False
        try:
            try:
                issues, parsed = parse_release_path(staged["path"])
            except OSError as exc:
                # 暂存包落在处理预览的那个实例本地，多副本部署下 apply 可能被路由到别的实例。
                logger.warning("collector release staging file unreadable: token=%s error_type=%s", token, type(exc).__name__)
                cache.delete(f"{C.STAGING_CACHE_PREFIX}{token}")
                raise ValidationAppException("预览暂存包已失效，请重新选择文件预览。", data={"code": PREVIEW_EXPIRED}) from exc
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
            failed_artifacts = []
            for artifact in parsed.artifacts:
                CollectorReleaseService._renew_import_lock(parsed.collector, token)
                try:
                    artifact_results.append(CollectorReleaseService._commit_one_artifact(parsed, artifact, keep_local_slots))
                except ValidationAppException as exc:
                    code = STORAGE_FAILED
                    if isinstance(exc.data, dict) and exc.data.get("code"):
                        code = exc.data["code"]
                    failed_artifacts.append(
                        {
                            "os": artifact.os,
                            "arch": artifact.arch,
                            "message": exc.message,
                            "code": code,
                        }
                    )
                except Exception as exc:
                    failed_artifacts.append(
                        {
                            "os": artifact.os,
                            "arch": artifact.arch,
                            "message": str(exc),
                            "code": STORAGE_FAILED,
                        }
                    )

            # 不管有没有架构失败，暂存包这一轮的用途都已经用完了；重试同一个包会
            # 重新走 preview 拿新 token，已成功的架构会因为哈希相同被跳过。
            cleanup_staging = True
            if artifact_results:
                CollectorReleaseService.refresh_collector_upgrade_hints(parsed.collector)

            if failed_artifacts:
                return {
                    "ok": False,
                    "collector": parsed.collector,
                    "version": parsed.version,
                    "artifacts": artifact_results,
                    "issues": [
                        issue(
                            item.get("code") or STORAGE_FAILED,
                            f"{item['os']}/{item['arch']} 写入失败：{item['message']}",
                            details=item,
                        ).to_dict()
                        for item in failed_artifacts
                    ],
                    "message": "部分架构写入失败，已成功的架构保持导入状态；监控插件尚未写入。重新导入同一个包会自动跳过已成功的架构。",
                }

            # 插件短事务放在全部目标架构成功之后：避免 pack_version 先钉死、
            # 二进制却只导入了一部分，内置迁移被跳过却没法用新包。
            CollectorReleaseService._renew_import_lock(parsed.collector, token)
            with transaction.atomic():
                plugin_result = CollectorReleaseService._import_plugin_payload(parsed, meta) or {}

            cache.delete(f"{C.STAGING_CACHE_PREFIX}{token}")
            plugin_name = ""
            if isinstance(parsed.metrics, dict):
                plugin_name = str(parsed.metrics.get("plugin") or "").strip()
            plugin_name = plugin_result.get("plugin") or plugin_name or parsed.collector
            plugin = MonitorPlugin.objects.filter(name=plugin_name).first()
            from apps.monitor.services.collect_config_update import CollectConfigUpdateService

            stale = CollectConfigUpdateService.stale_summary(
                plugin,
                actor_context,
                previous_fingerprint=plugin_result.get("previous_fingerprint") or "",
            )
            return {
                "ok": True,
                "collector": parsed.collector,
                "version": parsed.version,
                "artifacts": artifact_results,
                "issues": [item.to_dict() for item in all_issues if item.level != LEVEL_ERROR],
                "monitor_object_id": stale.get("monitor_object_id")
                or CollectorReleasePluginService.resolve_entry_monitor_object_id(
                    plugin_name=plugin_name,
                    collector=parsed.collector,
                ),
                "plugin_id": stale.get("plugin_id"),
                "stale_instance_count": stale.get("stale_instance_count") or 0,
                "first_fingerprint": bool(stale.get("first_fingerprint")),
                "message": "导入成功。已接入实例不会自动重下发。配置需更新与节点二进制可升级不是同一件事；节点二进制须再安装或升级。",
            }
        finally:
            CollectorReleaseService._release_import_lock(collector_name, token)
            if cleanup_staging:
                path = staged.get("path")
                if path:
                    shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    @staticmethod
    def _import_lock_key(collector_name: str) -> str:
        return f"{C.LOCK_CACHE_PREFIX}{collector_name}"

    @staticmethod
    def _acquire_import_lock(collector_name: str, owner: str) -> None:
        if not cache.add(CollectorReleaseService._import_lock_key(collector_name), owner, C.LOCK_TTL_SECONDS):
            raise ValidationAppException("同一采集器正在导入或恢复内置，请稍后重试。", data={"code": IMPORT_LOCKED})

    @staticmethod
    def _renew_import_lock(collector_name: str, owner: str) -> None:
        key = CollectorReleaseService._import_lock_key(collector_name)
        if cache.get(key) != owner:
            raise ValidationAppException("同一采集器正在导入或恢复内置，请稍后重试。", data={"code": IMPORT_LOCKED})
        cache.set(key, owner, C.LOCK_TTL_SECONDS)

    @staticmethod
    def _release_import_lock(collector_name: str, owner: str) -> None:
        key = CollectorReleaseService._import_lock_key(collector_name)
        if cache.get(key) == owner:
            cache.delete(key)

    @staticmethod
    def restore_builtin(collector_name: str, actor_context=None) -> dict:
        from apps.node_mgmt.services.collector_release.allowlist import load_builtin_collectors

        owner = f"restore:{uuid.uuid4().hex}"
        CollectorReleaseService._acquire_import_lock(collector_name, owner)
        try:
            plugin_result = CollectorReleasePluginService.restore_builtin(collector_name)
            builtins = {(item.get("node_operating_system"), item.get("cpu_architecture")): item for item in load_builtin_collectors(collector_name)}
            for collector in Collector.objects.filter(name=collector_name):
                builtin = builtins.get((collector.node_operating_system, collector.cpu_architecture))
                if builtin and builtin.get("execute_parameters") is not None:
                    collector.execute_parameters = builtin["execute_parameters"]
                collector.imported_package_version = ""
                collector.save(update_fields=["execute_parameters", "imported_package_version"])
            plugin = MonitorPlugin.objects.filter(name=plugin_result.get("plugin") or collector_name).first()
            from apps.monitor.services.collect_config_update import CollectConfigUpdateService

            stale = CollectConfigUpdateService.stale_summary(
                plugin,
                actor_context,
                previous_fingerprint=plugin_result.get("previous_fingerprint") or "",
            )
            return {
                "collector": collector_name,
                "plugin": plugin_result,
                "monitor_object_id": stale.get("monitor_object_id"),
                "plugin_id": stale.get("plugin_id"),
                "stale_instance_count": stale.get("stale_instance_count") or 0,
                "first_fingerprint": bool(stale.get("first_fingerprint")),
            }
        finally:
            CollectorReleaseService._release_import_lock(collector_name, owner)

    @staticmethod
    def refresh_collector_upgrade_hints(collector_name: str) -> None:
        collectors = {item.id: item for item in Collector.objects.filter(name=collector_name)}
        if not collectors:
            return
        # 只扫这一个采集器的历史包，不必每次导入都拉全平台所有采集器的全部版本（F3）。
        latest_map = VersionUpgradeService.get_latest_versions_map("collector", object_name=collector_name)
        changed = []
        for record in NodeComponentVersion.objects.filter(component_type="collector", component_id__in=list(collectors)):
            collector = collectors.get(record.component_id)
            if not collector:
                continue
            latest = ((latest_map.get(collector.node_operating_system) or {}).get(collector.name) or {}).get(collector.cpu_architecture or "", "")
            upgradeable = VersionUtils.is_upgradeable(record.version, latest)
            if record.latest_version == latest and record.upgradeable == upgradeable:
                continue
            record.latest_version = latest
            record.upgradeable = upgradeable
            changed.append(record)
        if changed:
            NodeComponentVersion.objects.bulk_update(changed, ["latest_version", "upgradeable"], batch_size=500)

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
