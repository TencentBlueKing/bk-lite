"""执行记录风险摘要应按任务链建索引，避免按风险项次数查询。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType, OSType
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, Patch, PatchTarget
from apps.patch_mgmt.services.execution_record_service import (
    build_risk_item_detail,
    build_risk_item_summaries,
)


def _count_sql(queries, *needles: str) -> int:
    return sum(1 for query in queries if all(needle in query["sql"] for needle in needles))


def _count_lookups(queries, column: str) -> int:
    markers = (f'{column}" IN ', f'{column}" =', f"{column} IN ", f"{column} = ")
    return sum(1 for query in queries if any(marker in query["sql"] for marker in markers))


def _risk_item(host_id: int, patch_id: int, host_name: str = "host", patch_name: str = "patch") -> dict:
    return {
        "id": f"{host_id}:{patch_id}:30",
        "host_id": host_id,
        "host_name": host_name,
        "host_ip": f"10.0.0.{host_id}",
        "patch_id": patch_id,
        "patch_name": patch_name,
    }


def _failed_multi_patch_root(patch_count: int) -> GovernanceTask:
    patches = [
        Patch.objects.create(title=f"patch-{index}", os_type=OSType.LINUX, team=[1])
        for index in range(patch_count)
    ]
    risk_snapshot = [
        _risk_item(10, patch.id, host_name="host-a", patch_name=patch.title) for patch in patches
    ]
    root = GovernanceTask.objects.create(
        name=f"治理 · host-a · {patch_count}项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.FAILED,
        target_list=[10],
        patch_list=[patch.id for patch in patches],
        risk_snapshot=risk_snapshot,
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root,
        target_id=10,
        target_name="host-a",
        stage="failed",
        can_retry=True,
    )
    return root


@pytest.mark.django_db
def test_failed_item_exists_queries_do_not_grow_with_risk_count():
    small_root = _failed_multi_patch_root(6)
    large_root = _failed_multi_patch_root(12)

    with CaptureQueriesContext(connection) as small_queries:
        small_summaries = build_risk_item_summaries(small_root)
    with CaptureQueriesContext(connection) as large_queries:
        large_summaries = build_risk_item_summaries(large_root)

    assert len(small_summaries) == 6
    assert len(large_summaries) == 12
    assert all(item["status"] == "failed" and item["can_retry"] for item in small_summaries)
    assert all(item["status"] == "failed" and item["can_retry"] for item in large_summaries)

    small_patch_queries = _count_sql(small_queries, "patch_patch")
    large_patch_queries = _count_sql(large_queries, "patch_patch")
    small_retry_queries = _count_lookups(small_queries, "source_risk_item_id")
    large_retry_queries = _count_lookups(large_queries, "source_risk_item_id")

    assert small_patch_queries <= 1
    assert large_patch_queries <= 1
    assert large_patch_queries <= small_patch_queries
    assert small_retry_queries <= 1
    assert large_retry_queries <= 1
    assert large_retry_queries <= small_retry_queries


@pytest.mark.django_db
def test_summary_status_and_can_retry_keep_failed_unmet_waiting_semantics():
    failed_patch = Patch.objects.create(title="failed-patch", os_type=OSType.LINUX, team=[1])
    unmet_patch = Patch.objects.create(title="unmet-patch", os_type=OSType.LINUX, team=[1])
    waiting_patch = Patch.objects.create(title="waiting-patch", os_type=OSType.LINUX, team=[1])
    missing_patch_id = failed_patch.id + unmet_patch.id + waiting_patch.id + 1000
    retried_patch = Patch.objects.create(title="retried-patch", os_type=OSType.LINUX, team=[1])
    host_failed = PatchTarget.objects.create(name="host-failed", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    host_unmet = PatchTarget.objects.create(name="host-unmet", ip="10.0.0.2", os_type=OSType.LINUX, team=[1])
    host_waiting = PatchTarget.objects.create(name="host-waiting", ip="10.0.0.3", os_type=OSType.LINUX, team=[1])
    host_missing = PatchTarget.objects.create(name="host-missing", ip="10.0.0.4", os_type=OSType.LINUX, team=[1])
    host_retried = PatchTarget.objects.create(name="host-retried", ip="10.0.0.5", os_type=OSType.LINUX, team=[1])
    host_running = PatchTarget.objects.create(name="host-running", ip="10.0.0.6", os_type=OSType.LINUX, team=[1])

    failed_item = _risk_item(host_failed.id, failed_patch.id, "host-failed", failed_patch.title)
    unmet_item = _risk_item(host_unmet.id, unmet_patch.id, "host-unmet", unmet_patch.title)
    waiting_item = _risk_item(host_waiting.id, waiting_patch.id, "host-waiting", waiting_patch.title)
    missing_item = _risk_item(host_missing.id, missing_patch_id, "host-missing", "gone")
    retried_item = _risk_item(host_retried.id, retried_patch.id, "host-retried", retried_patch.title)
    running_item = _risk_item(host_running.id, waiting_patch.id, "host-running", waiting_patch.title)

    root = GovernanceTask.objects.create(
        name="治理 · 多主机",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[
            host_failed.id,
            host_unmet.id,
            host_waiting.id,
            host_missing.id,
            host_retried.id,
            host_running.id,
        ],
        patch_list=[failed_patch.id, unmet_patch.id, waiting_patch.id, missing_patch_id, retried_patch.id],
        risk_snapshot=[failed_item, unmet_item, waiting_item, missing_item, retried_item, running_item],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host_failed.id, target_name="host-failed", stage="failed", can_retry=True
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host_unmet.id, target_name="host-unmet", stage="completed", can_retry=False
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host_waiting.id, target_name="host-waiting", stage="completed", can_retry=False
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host_missing.id, target_name="host-missing", stage="failed", can_retry=True
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host_retried.id, target_name="host-retried", stage="failed", can_retry=True
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host_running.id, target_name="host-running", stage="installing", can_retry=False
    )
    verify = GovernanceTask.objects.create(
        name="自动验证",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.COMPLETED,
        parent_task=root,
        target_list=[host_unmet.id],
        patch_list=[unmet_patch.id],
        result_snapshot=[
            {
                "risk_item_id": unmet_item["id"],
                "host_id": host_unmet.id,
                "patch_id": unmet_patch.id,
                "status": "completed",
                "satisfied": False,
            }
        ],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=verify, target_id=host_unmet.id, target_name="host-unmet", stage="completed", can_retry=False
    )
    GovernanceTask.objects.create(
        name="重试",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.PENDING,
        parent_task=None,
        source_record=root,
        source_risk_item_id=retried_item["id"],
        team=[1],
    )

    summaries = {item["id"]: item for item in build_risk_item_summaries(root)}

    assert summaries[failed_item["id"]]["status"] == "failed"
    assert summaries[failed_item["id"]]["can_retry"] is True
    assert summaries[unmet_item["id"]]["status"] == "unmet"
    assert summaries[unmet_item["id"]]["can_retry"] is True
    assert summaries[waiting_item["id"]]["status"] == "waiting"
    assert summaries[waiting_item["id"]]["can_retry"] is False
    assert summaries[missing_item["id"]]["status"] == "failed"
    assert summaries[missing_item["id"]]["can_retry"] is False
    assert summaries[retried_item["id"]]["status"] == "failed"
    assert summaries[retried_item["id"]]["can_retry"] is False
    assert summaries[running_item["id"]]["status"] == "running"
    assert summaries[running_item["id"]]["can_retry"] is False


@pytest.mark.django_db
def test_sparse_host_patch_verification_and_later_manual_action_stay_isolated():
    host = PatchTarget.objects.create(name="host-sparse", ip="10.0.0.7", os_type=OSType.LINUX, team=[1])
    completed_patch = Patch.objects.create(title="completed-patch", os_type=OSType.LINUX, team=[1])
    unmet_patch = Patch.objects.create(title="unmet-patch", os_type=OSType.LINUX, team=[1])
    completed_item = _risk_item(host.id, completed_patch.id, "host-sparse", completed_patch.title)
    unmet_item = _risk_item(host.id, unmet_patch.id, "host-sparse", unmet_patch.title)
    root = GovernanceTask.objects.create(
        name="治理 · 稀疏项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[host.id],
        patch_list=[completed_patch.id, unmet_patch.id],
        risk_snapshot=[completed_item, unmet_item],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host.id, target_name="host-sparse", stage="completed", can_retry=False
    )
    verify = GovernanceTask.objects.create(
        name="自动验证",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.COMPLETED,
        parent_task=root,
        target_list=[host.id],
        patch_list=[completed_patch.id, unmet_patch.id],
        result_snapshot=[
            {
                "risk_item_id": completed_item["id"],
                "host_id": host.id,
                "patch_id": completed_patch.id,
                "status": "completed",
                "satisfied": True,
            },
            {
                "risk_item_id": unmet_item["id"],
                "host_id": host.id,
                "patch_id": unmet_patch.id,
                "status": "completed",
                "satisfied": False,
            },
        ],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=verify, target_id=host.id, target_name="host-sparse", stage="completed"
    )
    later_reboot = GovernanceTask.objects.create(
        name="后续手动重启",
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.COMPLETED,
        source_record=root,
        target_list=[host.id],
        risk_snapshot=[{**completed_item, "source_record_id": root.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=later_reboot, target_id=host.id, target_name="host-sparse", stage="completed"
    )

    summaries = {item["id"]: item for item in build_risk_item_summaries(root)}
    visible_root = GovernanceTask.objects.get(pk=root.id)
    visible_root._visible_target_ids = set()

    assert summaries[completed_item["id"]]["status"] == "completed"
    assert summaries[completed_item["id"]]["can_retry"] is False
    assert summaries[unmet_item["id"]]["status"] == "unmet"
    assert summaries[unmet_item["id"]]["can_retry"] is True
    assert build_risk_item_summaries(visible_root) == []


@pytest.mark.django_db
def test_detail_status_and_can_retry_share_summary_index():
    patch = Patch.objects.create(title="retry-patch", os_type=OSType.LINUX, team=[1])
    host = PatchTarget.objects.create(name="host-a", ip="10.0.0.8", os_type=OSType.LINUX, team=[1])
    item = _risk_item(host.id, patch.id, "host-a", patch.title)
    root = GovernanceTask.objects.create(
        name="治理 · host-a · 1项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.FAILED,
        target_list=[host.id],
        patch_list=[patch.id],
        risk_snapshot=[item],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root, target_id=host.id, target_name="host-a", stage="failed", can_retry=True, log="install failed"
    )

    summary = build_risk_item_summaries(root)[0]
    detail = build_risk_item_detail(root, item["id"])

    assert detail["status"] == summary["status"] == "failed"
    assert detail["can_retry"] is summary["can_retry"] is True
    assert detail["steps"][0]["attempts"][-1]["log"] == "install failed"
