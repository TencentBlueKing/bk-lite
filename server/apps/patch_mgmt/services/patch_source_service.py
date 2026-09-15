"""补丁源域服务"""

from typing import Optional

from apps.core.logger import patch_mgmt_logger as logger
from apps.patch_mgmt.constants import ConnectivityStatus, OSType, PatchSourceType
from apps.patch_mgmt.models import PatchSource
from django.db import transaction
from django.db.models import F
from django.utils import timezone


class PatchSourceService:
    """补丁源配置域服务

    职责：
      - 启用/停用补丁源
      - 更新连通性状态
      - 字段完整性校验（不涉及网络探测）
      - 已启用源列表过滤
    不涉及：网络探测任务、Celery 调度。
    """

    @staticmethod
    def enable(source: PatchSource) -> None:
        """启用补丁源；已启用时为幂等操作。"""
        if source.is_enabled:
            return
        source.is_enabled = True
        source.save(update_fields=["is_enabled", "updated_at"])
        logger.info("PatchSource enabled: id=%s name=%s", source.pk, source.name)

    @staticmethod
    def disable(source: PatchSource) -> None:
        """停用补丁源；已停用时为幂等操作。"""
        if not source.is_enabled:
            return
        source.is_enabled = False
        source.save(update_fields=["is_enabled", "updated_at"])
        logger.info("PatchSource disabled: id=%s name=%s", source.pk, source.name)

    @staticmethod
    def reset_connectivity_after_config_change(source: PatchSource) -> int:
        """连接配置变更：同一事务递增 revision 并重置为 UNKNOWN。"""
        now = timezone.now()
        with transaction.atomic():
            PatchSource.objects.filter(pk=source.pk).update(
                connectivity_status=ConnectivityStatus.UNKNOWN,
                last_checked_at=None,
                connectivity_revision=F("connectivity_revision") + 1,
                updated_at=now,
            )
        source.refresh_from_db()
        return source.connectivity_revision

    @staticmethod
    def update_connectivity(
        source: PatchSource,
        status: str,
        checked_at=None,
        revision=None,
    ) -> bool:
        """按 source_id+revision 条件更新连通性状态。

        Args:
            source: 补丁源实例。
            status: ConnectivityStatus 枚举值。
            checked_at: 检测时间；None 时取 timezone.now()。
            revision: 探测开始时的配置版本。未传且当前 revision>0 时 fail-closed。

        Raises:
            ValueError: status 不在合法枚举范围内。
        """
        valid = {c for c, _ in ConnectivityStatus.CHOICES}
        if status not in valid:
            raise ValueError(
                f"无效的连通性状态: {status!r}，合法值: {sorted(valid)}"
            )
        now = checked_at or timezone.now()
        qs = PatchSource.objects.filter(pk=source.pk)
        if revision is None:
            current = qs.values_list("connectivity_revision", flat=True).first()
            if current is None:
                return False
            if current > 0:
                logger.info(
                    "PatchSource connectivity write skipped: source_id=%s missing revision current_revision=%s",
                    source.pk,
                    current,
                )
                return False
        else:
            qs = qs.filter(connectivity_revision=revision)
        updated = qs.update(
            connectivity_status=status,
            last_checked_at=now,
            updated_at=timezone.now(),
        )
        if updated:
            source.connectivity_status = status
            source.last_checked_at = now
        return bool(updated)

    @staticmethod
    def validate_source_fields(source: PatchSource) -> None:
        """校验源类型必填字段完整性。

        WSUS：url 不能为空。
        Linux (yum/dnf/apt)：distro_name 和 os_version 均不能为空。

        Raises:
            ValueError: 必填字段缺失。
        """
        if source.source_type in PatchSourceType.WINDOWS_TYPES:
            if not source.url:
                raise ValueError("Windows 补丁源必须提供 URL")
        elif source.source_type in PatchSourceType.LINUX_TYPES:
            if not source.distro_name:
                raise ValueError("Linux 补丁源必须提供发行版名称(distro_name)")
            if not source.os_version:
                raise ValueError("Linux 补丁源必须提供系统版本(os_version)")

    @staticmethod
    def list_enabled(os_type: Optional[str] = None):
        """返回已启用补丁源的 QuerySet，可按 OS 类型过滤。

        Args:
            os_type: OSType.WINDOWS 或 OSType.LINUX；None 表示不过滤。

        Returns:
            PatchSource QuerySet（已启用，按 os_type 过滤）。
        """
        qs = PatchSource.objects.filter(is_enabled=True)
        if os_type == OSType.WINDOWS:
            qs = qs.filter(source_type__in=PatchSourceType.WINDOWS_TYPES)
        elif os_type == OSType.LINUX:
            qs = qs.filter(source_type__in=PatchSourceType.LINUX_TYPES)
        return qs
