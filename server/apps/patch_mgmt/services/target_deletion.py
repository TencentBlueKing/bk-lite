"""删除补丁目标时清理该主机的全部补丁业务数据。"""

from django.db.models import Q

from apps.core.utils.viewset_utils import build_json_membership_query
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost


def _matches_id(value, expected: int) -> bool:
    try:
        return int(value) == expected
    except (TypeError, ValueError):
        return False


def _without_target(items, target_id: int) -> list:
    return [
        item
        for item in (items or [])
        if not isinstance(item, dict)
        or not _matches_id(
            item.get("host_id") or item.get("target_id"), target_id
        )
    ]


def purge_target_governance_history(target_id: int) -> None:
    """裁剪多主机任务，并删除已无主机的整条任务数据。

    调用方必须处于 transaction.atomic 中。
    """
    task_membership = build_json_membership_query(
        GovernanceTask.objects.all(), "target_list", [target_id]
    )
    task_ids = list(
        GovernanceTask.objects.filter(
            task_membership | Q(host_results__target_id=target_id)
        )
        .order_by()
        .values_list("id", flat=True)
        .distinct()
    )
    if not task_ids:
        GovernanceTaskHost.objects.filter(target_id=target_id).delete()
        return

    tasks = list(
        GovernanceTask.objects.select_for_update()
        .filter(pk__in=task_ids)
        .order_by("id")
    )
    GovernanceTaskHost.objects.filter(target_id=target_id).delete()

    delete_ids: list[int] = []
    for task in tasks:
        task.target_list = [
            value
            for value in (task.target_list or [])
            if not _matches_id(value, target_id)
        ]
        task.risk_snapshot = _without_target(task.risk_snapshot, target_id)
        task.result_snapshot = _without_target(task.result_snapshot, target_id)
        remaining_target_ids = set(task.target_list) | set(
            task.host_results.values_list("target_id", flat=True)
        )
        if not remaining_target_ids:
            delete_ids.append(task.id)
            continue

        remaining_patch_ids = []
        for item in [*(task.risk_snapshot or []), *(task.result_snapshot or [])]:
            if not isinstance(item, dict) or not item.get("patch_id"):
                continue
            try:
                remaining_patch_ids.append(int(item["patch_id"]))
            except (TypeError, ValueError):
                continue
        task.patch_list = list(dict.fromkeys(remaining_patch_ids))
        task.save(
            update_fields=[
                "target_list",
                "patch_list",
                "risk_snapshot",
                "result_snapshot",
                "updated_at",
            ]
        )

    if delete_ids:
        GovernanceTask.objects.filter(pk__in=delete_ids).delete()
