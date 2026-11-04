"""分发文件生命周期辅助。"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.job_mgmt.models import DistributionFile

WORKFLOW_FILE_RENEW_DAYS = 90


def renew_distribution_files(*, file_keys: list[str], team_ids: list[int], days: int = WORKFLOW_FILE_RENEW_DAYS) -> int:
    """将指定团队下的分发文件续期；不存在或不属于团队的 key 静默跳过。"""
    keys = [str(item).strip() for item in file_keys if str(item).strip()]
    teams = [int(item) for item in team_ids if str(item).lstrip("-").isdigit() and int(item) > 0]
    if not keys or not teams:
        return 0
    expire_at = timezone.now() + timedelta(days=max(1, min(int(days), 365)))
    return DistributionFile.objects.filter(file_key__in=keys, team__in=teams).update(expire_at=expire_at)
