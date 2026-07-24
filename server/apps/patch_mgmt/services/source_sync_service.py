"""补丁源同步入口服务

職責：连通性探测触发/结果记录（数据路径）、Windows/Linux 源同步派发入口。
不涉及：实际网络 I/O、补丁下载。实际探测与同步执行由调用方（Celery task）负责接入。
"""

import logging
from typing import Optional

from django.utils import timezone

from apps.patch_mgmt.constants import ConnectivityStatus, OSType, PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.services.patch_source_service import PatchSourceService

logger = logging.getLogger("app")


class SourceSyncError(Exception):
    """补丁源同步异常基类"""


class SourceSyncService:
    """补丁源同步入口服务

    连通性探测为异步两段式：
      1. trigger_connectivity_check() → 重置状态为 UNKNOWN，派发 Celery 任务（任务由 tasks.py 调用）
      2. record_connectivity_result() → Celery 任务完成后写回结果

    源同步同理：trigger_* 校验源类型并写日志，实际 Celery 任务派发由调用方接入。
    """

    @classmethod
    def trigger_connectivity_check(cls, source: PatchSource) -> None:
        """触发连通性探测：重置状态为 UNKNOWN 并记录日志。

        Celery 任务（check_patch_source_connectivity）完成探测后应调用
        record_connectivity_result 回写结果。

        Args:
            source: 补丁源实例。
        """
        PatchSourceService.update_connectivity(source, ConnectivityStatus.UNKNOWN)
        logger.info(
            "SourceSyncService: connectivity check triggered source_id=%s name=%s",
            source.pk, source.name,
        )

    @classmethod
    def record_connectivity_result(
        cls,
        source: PatchSource,
        reachable: bool,
        checked_at=None,
    ) -> None:
        """记录源连通性探测结果（由 Celery 任务完成后回调）。

        Args:
            source: 补丁源实例。
            reachable: True → CONNECTED；False → FAILED。
            checked_at: 探测完成时间；None 取 timezone.now()。
        """
        status = ConnectivityStatus.CONNECTED if reachable else ConnectivityStatus.FAILED
        PatchSourceService.update_connectivity(
            source, status, checked_at=checked_at or timezone.now()
        )
        logger.info(
            "SourceSyncService: connectivity result recorded source_id=%s reachable=%s",
            source.pk, reachable,
        )

    @classmethod
    def trigger_windows_sync(cls, source: PatchSource) -> None:
        """触发 WSUS 源同步入口。

        校验源类型并写日志后返回；调用方负责在此之后派发 Celery 任务执行
        实际同步逻辑（远程元数据获取、解析与入库）。

        Args:
            source: Windows 类型补丁源。

        Raises:
            SourceSyncError: source 不是 Windows 类型。
        """
        if not source.is_windows_source:
            raise SourceSyncError(
                f"补丁源 {source.pk} ({source.source_type!r}) 不是 Windows 类型，"
                "无法触发 Windows 源同步"
            )
        logger.info(
            "SourceSyncService: Windows sync triggered source_id=%s type=%s",
            source.pk, source.source_type,
        )

    @classmethod
    def sync_wsus(cls, source: PatchSource) -> dict:
        """同步 WSUS 源的已批准补丁到补丁库。

        流程: WinRM + PowerShell 获取批准补丁 -> Patch + WindowsPatchDetail 元数据入库。

        Returns:
            {"total": int, "created": int, "updated": int}
        Raises:
            SourceSyncError: 源类型不是 WSUS。
            WsusSyncError: WSUS 连接失败或同步异常（由调用方捕获）。
        """
        from apps.patch_mgmt.constants import PatchSourceType
        from apps.patch_mgmt.services.wsus_sync import WsusSyncError, sync_wsus

        if source.source_type != PatchSourceType.WSUS:
            raise SourceSyncError(
                f"补丁源 {source.pk} ({source.source_type!r}) 不是 WSUS 类型"
            )
        result = sync_wsus(source)
        logger.info(
            "SourceSyncService.sync_wsus: source_id=%s result=%s",
            source.pk, result,
        )
        return result

    @classmethod
    def sync_linux_repo(cls, source: PatchSource) -> dict:
        """同步 Linux yum/dnf repo 的安全公告元数据到补丁库(仅元数据,不下载包)。

        每条 updateinfo <update> 落为一条 Patch(以 source+advisory_id 去重)+ LinuxPatchDetail。
        Patch.team 取自补丁源；同步成功后 pkg_status 设为 READY。

        Returns:
            {"total": 解析公告数, "created": 新建, "updated": 更新}
        Raises:
            SourceSyncError: 源类型不对。
            RepoSyncError: 网络/解析失败(由调用方捕获)。
        """
        from apps.patch_mgmt.constants import OSType, PackageStatus, PatchSeverity, PatchType
        from apps.patch_mgmt.models import LinuxPatchDetail, Patch
        from apps.patch_mgmt.services.linux_repo_sync import fetch_advisories

        if not source.is_linux_source:
            raise SourceSyncError(
                f"补丁源 {source.pk} ({source.source_type!r}) 不是 Linux 类型,无法同步"
            )

        advisories = fetch_advisories(source)
        sev_map = {
            "critical": PatchSeverity.CRITICAL,
            "important": PatchSeverity.IMPORTANT,
            "moderate": PatchSeverity.MODERATE,
            "low": PatchSeverity.LOW,
        }
        created = updated = 0
        now = timezone.now()
        for adv in advisories:
            patch_type = PatchType.SECURITY if adv.adv_type == "security" else PatchType.GENERIC
            severity = sev_map.get(adv.severity.lower(), PatchSeverity.MODERATE) if adv.severity else PatchSeverity.MODERATE
            patch, is_new = Patch.objects.get_or_create(
                title=adv.advisory_id,
                os_type=OSType.LINUX,
                defaults={
                    "patch_type": patch_type,
                    "severity": severity,
                    "cve_list": adv.cve_list,
                    "team": list(source.team or []),
                    "pkg_status": PackageStatus.READY,
                    "released_at": None,
                },
            )
            patch.sources.add(source)
            # 同步成功后统一标记为就绪，安装时再从源下载。
            patch.patch_type = patch_type
            patch.severity = severity
            patch.cve_list = adv.cve_list
            patch.pkg_status = PackageStatus.READY
            patch.last_synced_at = now
            patch.save(update_fields=["patch_type", "severity", "cve_list", "pkg_status", "last_synced_at", "updated_at"])

            first_pkg = adv.packages[0] if adv.packages else None
            LinuxPatchDetail.objects.update_or_create(
                patch=patch,
                defaults={
                    "pkg_name": first_pkg.name if first_pkg else "",
                    "pkg_version": first_pkg.version if first_pkg else "",
                    "distro_name": source.distro_name or "",
                    "os_version_range": source.os_version or "",
                    "architectures": sorted({p.arch for p in adv.packages if p.arch}),
                    "repo_type": source.source_type,
                    "install_deps": adv.install_deps or {},
                },
            )
            if is_new:
                created += 1
            else:
                updated += 1

        logger.info(
            "SourceSyncService.sync_linux_repo: source_id=%s total=%s created=%s updated=%s",
            source.pk, len(advisories), created, updated,
        )
        return {"total": len(advisories), "created": created, "updated": updated}

    @classmethod
    def trigger_linux_sync(cls, source: PatchSource) -> None:
        """触发 Linux repo 源同步入口。

        校验源类型并写日志后返回；调用方负责在此之后派发 Celery 任务执行
        实际同步逻辑（repodata 解析、LinuxPatchDetail 更新）。

        Args:
            source: Linux 类型补丁源。

        Raises:
            SourceSyncError: source 不是 Linux 类型。
        """
        if not source.is_linux_source:
            raise SourceSyncError(
                f"补丁源 {source.pk} ({source.source_type!r}) 不是 Linux 类型，"
                "无法触发 Linux 源同步"
            )
        logger.info(
            "SourceSyncService: Linux sync triggered source_id=%s type=%s",
            source.pk, source.source_type,
        )

    @classmethod
    def list_sources_for_sync(cls, os_type: Optional[str] = None):
        """返回启用的可触发同步源列表。

        Args:
            os_type: OSType.WINDOWS / OSType.LINUX；None 表示不过滤。

        Returns:
            PatchSource QuerySet（已启用）。
        """
        return PatchSourceService.list_enabled(os_type=os_type)

    @classmethod
    def preview_sync_candidates(cls, source: PatchSource) -> list:
        """从补丁源拉取候选补丁列表（不写库），供前端「同步入库」抽屉展示。

        Returns:
            [{"key", "name", "title", "version", "dist", "arch", "added", "severity"}, ...]
        Raises:
            SourceSyncError / RepoSyncError / WsusSyncError
        """
        from apps.patch_mgmt.constants import OSType, PatchSourceType
        from apps.patch_mgmt.models import Patch

        if source.is_linux_source:
            from apps.patch_mgmt.services.linux_repo_sync import fetch_advisories

            advisories = fetch_advisories(source)
            existing_titles = set(
                Patch.objects.filter(os_type=OSType.LINUX)
                .values_list("title", flat=True)
            )
            candidates = []
            for adv in advisories:
                first_pkg = adv.packages[0] if adv.packages else None
                candidates.append({
                    "key": adv.advisory_id,
                    "name": first_pkg.name if first_pkg else adv.advisory_id,
                    "title": adv.title,
                    "version": first_pkg.version if first_pkg else "",
                    "dist": source.distro_name or "",
                    "arch": (first_pkg.arch if first_pkg and first_pkg.arch else source.arch or ""),
                    "added": adv.advisory_id in existing_titles or adv.title in existing_titles,
                    "severity": adv.severity or "",
                })
            return candidates

        if source.source_type == PatchSourceType.WSUS:
            from apps.patch_mgmt.services.wsus_sync import WsusClient

            client = WsusClient(source)
            updates = client.get_approved_updates()
            existing_titles = set(
                Patch.objects.filter(os_type=OSType.WINDOWS)
                .values_list("title", flat=True)
            )
            candidates = []
            for upd in updates:
                name = upd.kb_number or upd.title or upd.update_id
                candidates.append({
                    "key": upd.update_id,
                    "name": name,
                    "title": upd.title,
                    "version": ", ".join(upd.products[:3]) if upd.products else "",
                    "dist": "",
                    "arch": source.arch or "x64",
                    "added": name in existing_titles or upd.title in existing_titles,
                })
            return candidates

        raise SourceSyncError(f"源类型 {source.source_type!r} 不支持预览同步")

    @classmethod
    def ingest_selected(cls, source: PatchSource, keys: list, severity_overrides: dict = None) -> dict:
        """将选中的候选补丁入库（创建 Patch 记录）。

        Args:
            source: 补丁源实例。
            keys: 选中的候选 key 列表（advisory_id 或 update_id）。
            severity_overrides: 前端传入的严重级别覆盖，{advisory_id: severity_value}。

        Returns:
            {"created": N, "updated": N, "skipped": N, "total": N}
        """
        severity_overrides = severity_overrides or {}
        from apps.patch_mgmt.constants import (
            OSType,
            PackageStatus,
            PatchType,
            PatchSeverity,
        )
        from apps.patch_mgmt.models import Patch, WindowsPatchDetail, LinuxPatchDetail
        from apps.patch_mgmt.services.linux_repo_sync import fetch_advisories

        key_set = set(keys)
        created = updated = skipped = 0
        now = timezone.now()

        if source.is_linux_source:
            advisories = fetch_advisories(source)
            sev_map = {
                "critical": PatchSeverity.CRITICAL,
                "important": PatchSeverity.IMPORTANT,
                "moderate": PatchSeverity.MODERATE,
                "low": PatchSeverity.LOW,
            }
            for adv in advisories:
                if adv.advisory_id not in key_set:
                    continue
                patch_type = PatchType.SECURITY if adv.adv_type == "security" else PatchType.GENERIC
                # 优先用前端传入的 severity，其次用源数据 severity，最后默认中等
                override = severity_overrides.get(adv.advisory_id)
                if override:
                    severity = override
                elif adv.severity:
                    severity = sev_map.get(adv.severity.lower(), PatchSeverity.MODERATE)
                else:
                    severity = PatchSeverity.MODERATE
                patch, is_new = Patch.objects.get_or_create(
                    title=adv.advisory_id,
                    os_type=OSType.LINUX,
                    defaults={
                        "patch_type": patch_type,
                        "severity": severity,
                        "cve_list": adv.cve_list,
                        "team": list(source.team or []),
                        "pkg_status": PackageStatus.READY,
                    },
                )
                patch.sources.add(source)
                patch.patch_type = patch_type
                patch.severity = severity
                patch.cve_list = adv.cve_list
                patch.pkg_status = PackageStatus.READY
                patch.last_synced_at = now
                patch.save(update_fields=["patch_type", "severity", "cve_list", "pkg_status", "last_synced_at", "updated_at"])

                first_pkg = adv.packages[0] if adv.packages else None
                LinuxPatchDetail.objects.update_or_create(
                    patch=patch,
                    defaults={
                        "pkg_name": first_pkg.name if first_pkg else "",
                        "pkg_version": first_pkg.version if first_pkg else "",
                        "distro_name": source.distro_name or "",
                        "os_version_range": source.os_version or "",
                        "architectures": sorted({p.arch for p in adv.packages if p.arch}),
                        "repo_type": source.source_type,
                        "install_deps": adv.install_deps or {},
                    },
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

        elif source.source_type == "wsus":
            from apps.patch_mgmt.services.wsus_sync import WsusClient, resolve_wsus_patch

            client = WsusClient(source)
            updates = client.get_approved_updates()
            sev_map = {
                "critical": "critical",
                "important": "important",
                "moderate": "moderate",
                "low": "low",
            }
            for upd in updates:
                if upd.update_id not in key_set:
                    continue
                override = severity_overrides.get(upd.update_id)
                if override:
                    severity = override
                else:
                    severity = sev_map.get((upd.severity or "").lower(), "unspecified")
                patch, is_new, manual_conflict, normalized_kb = resolve_wsus_patch(
                    source,
                    upd,
                    {
                        "patch_type": PatchType.SECURITY,
                        "severity": severity,
                        "cve_list": [],
                        "team": list(source.team or []),
                        "pkg_status": PackageStatus.READY,
                    },
                )
                if manual_conflict:
                    skipped += 1
                    continue
                patch.sources.add(source)
                patch.patch_type = PatchType.SECURITY
                patch.severity = severity
                patch.pkg_status = PackageStatus.READY
                patch.last_synced_at = now
                patch.save(update_fields=["patch_type", "severity", "pkg_status", "last_synced_at", "updated_at"])

                WindowsPatchDetail.objects.update_or_create(
                    patch=patch,
                    defaults={
                        "kb_number": normalized_kb,
                        "product_list": upd.products or [],
                        "ms_bulletin": (upd.security_bulletins[0] if upd.security_bulletins else ""),
                    },
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
        else:
            raise SourceSyncError(f"源类型 {source.source_type!r} 不支持入库")

        total = created + updated + skipped
        logger.info(
            "SourceSyncService.ingest_selected: source_id=%s total=%s created=%s updated=%s skipped=%s",
            source.pk, total, created, updated, skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped, "total": total}
