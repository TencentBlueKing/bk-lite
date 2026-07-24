"""执行记录聚合与基线批量评估的公开 API 行为测试。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType, OSType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    Patch,
    PatchBaseline,
    PatchTarget,
)
from apps.patch_mgmt.services.governance_service import HostBusyError, create_remediation_task, create_retry_task
from apps.patch_mgmt.services.execution_record_service import build_record_status, build_risk_item_summaries
from apps.patch_mgmt.services.patch_execution_service import run_governance_host


BASE_URL = "/api/v1/patch_mgmt"
GOVERNANCE_URL = f"{BASE_URL}/api/governance/"
BASELINE_URL = f"{BASE_URL}/api/baseline/"


@pytest.mark.django_db
class TestExecutionRecordListApi:
    def test_list_only_exposes_root_remediation_and_reboot_records(self, su_client, mocker):
        mocker.patch(
            "apps.core.utils.viewset_utils.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )
        remediation = GovernanceTask.objects.create(
            name="治理 · 1台 · 1项",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.PENDING,
            team=[1],
        )
        GovernanceTask.objects.create(
            name="评估 · 主机A",
            task_type=GovernanceTaskType.ASSESS,
            status=GovernanceTaskStatus.COMPLETED,
            team=[1],
        )
        GovernanceTask.objects.create(
            name="自动验证",
            task_type=GovernanceTaskType.VERIFY,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=remediation,
            team=[1],
        )
        reboot = GovernanceTask.objects.create(
            name="重启 · 主机A",
            task_type=GovernanceTaskType.REBOOT,
            status=GovernanceTaskStatus.PENDING,
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=remediation,
            target_id=1,
            target_name="主机A",
            stage="waiting",
        )

        response = su_client.get(GOVERNANCE_URL)
        governance_only = su_client.get(GOVERNANCE_URL, {"task_type": "install"})

        assert response.status_code == status.HTTP_200_OK
        rows = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        assert [row["id"] for row in rows] == [reboot.id, remediation.id]
        assert [row["task_type_display"] for row in rows] == ["重启", "治理"]
        assert rows[1]["can_cancel"] is True
        governance_rows = (
            governance_only.data.get("results", governance_only.data)
            if isinstance(governance_only.data, dict)
            else governance_only.data
        )
        assert [row["id"] for row in governance_rows] == [remediation.id]

    def test_detail_returns_risk_summaries_and_selected_item_step_logs(self, su_client, mocker):
        mocker.patch(
            "apps.core.utils.viewset_utils.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )
        risk_id = "10:20:30"
        remediation = GovernanceTask.objects.create(
            name="治理 · host-a · 1项",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.COMPLETED,
            target_list=[10],
            patch_list=[20],
            risk_snapshot=[{
                "id": risk_id,
                "host_id": 10,
                "host_name": "host-a",
                "host_ip": "10.0.0.1",
                "patch_id": 20,
                "patch_name": "openssl",
                "baseline_id": 30,
                "baseline_name": "Linux 基线",
            }],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=remediation,
            target_id=10,
            target_name="host-a",
            stage="pending_reboot",
            log="install line 1\ninstall line 2",
        )
        reboot = GovernanceTask.objects.create(
            name="自动重启",
            task_type=GovernanceTaskType.REBOOT,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=remediation,
            target_list=[10],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=reboot,
            target_id=10,
            target_name="host-a",
            stage="completed",
            log="reboot line",
        )
        verify = GovernanceTask.objects.create(
            name="自动验证",
            task_type=GovernanceTaskType.VERIFY,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=reboot,
            target_list=[10],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=verify,
            target_id=10,
            target_name="host-a",
            stage="completed",
            log="verify line",
        )

        response = su_client.get(f"{GOVERNANCE_URL}{remediation.id}/")
        selected = su_client.get(
            f"{GOVERNANCE_URL}{remediation.id}/risk-item-detail/",
            {"risk_item_id": risk_id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["record_status"] == "completed"
        assert response.data["record_status_display"] == "已完成"
        assert response.data["risk_items"] == [{
            "id": risk_id,
            "display_name": "host-a-openssl",
            "host_id": 10,
            "patch_id": 20,
            "status": "completed",
            "status_display": "已完成",
            "status_color": "success",
        }]
        assert selected.status_code == status.HTTP_200_OK
        assert [step["key"] for step in selected.data["steps"]] == ["install", "reboot", "verify"]
        assert [step["attempts"][-1]["log"] for step in selected.data["steps"]] == [
            "install line 1\ninstall line 2",
            "reboot line",
            "verify line",
        ]

    def test_install_failure_is_not_overwritten_by_successful_validation(self):
        """后续验证成功只说明当前合规，不能把本次治理的安装失败改写为完成。"""
        risk_id = "10:20:30"
        remediation = GovernanceTask.objects.create(
            name="治理 · host-a · 1项",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.FAILED,
            target_list=[10],
            patch_list=[20],
            risk_snapshot=[{
                "id": risk_id,
                "host_id": 10,
                "host_name": "host-a",
                "patch_id": 20,
                "patch_name": "KB6000008",
            }],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=remediation,
            target_id=10,
            target_name="host-a",
            stage="failed",
            failed_stage=GovernanceTaskType.INSTALL,
            reason="schtasks warning",
        )
        verify = GovernanceTask.objects.create(
            name="安装后自动验证",
            task_type=GovernanceTaskType.VERIFY,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=remediation,
            target_list=[10],
            patch_list=[20],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=verify,
            target_id=10,
            target_name="host-a",
            stage="completed",
        )

        summaries = build_risk_item_summaries(remediation)

        assert summaries[0]["status"] == "failed"
        assert build_record_status(remediation) == ("failed", "失败", "error")

    def test_newer_retry_pending_reboot_is_not_overwritten_by_old_validation(self):
        """重试安装的待重启比旧验证更新，执行记录应展示待重启。"""
        risk_id = "10:20:30"
        remediation = GovernanceTask.objects.create(
            name="治理 · host-a · 1项",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.FAILED,
            target_list=[10],
            patch_list=[20],
            risk_snapshot=[{
                "id": risk_id,
                "host_id": 10,
                "host_name": "host-a",
                "patch_id": 20,
                "patch_name": "KB6000009",
            }],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=remediation,
            target_id=10,
            target_name="host-a",
            stage="failed",
            failed_stage=GovernanceTaskType.INSTALL,
        )
        old_verify = GovernanceTask.objects.create(
            name="旧验证",
            task_type=GovernanceTaskType.VERIFY,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=remediation,
            target_list=[10],
            patch_list=[20],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=old_verify,
            target_id=10,
            target_name="host-a",
            stage="completed",
        )
        retry = GovernanceTask.objects.create(
            name="重试安装",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=remediation,
            target_list=[10],
            patch_list=[20],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=retry,
            target_id=10,
            target_name="host-a",
            stage="pending_reboot",
        )

        summaries = build_risk_item_summaries(remediation)

        assert summaries[0]["status"] == "pending_reboot"
        assert build_record_status(remediation) == ("pending_reboot", "待重启", "warning")


@pytest.mark.django_db
def test_remediation_snapshot_preserves_exact_selected_host_patch_pairs(
    request_factory, authenticated_user, mocker
):
    baseline = PatchBaseline.objects.create(name="Linux 基线", os_type=OSType.LINUX, team=[1])
    host_a = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    host_b = PatchTarget.objects.create(name="host-b", ip="10.0.0.2", os_type=OSType.LINUX, team=[1])
    patch_a = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    patch_b = Patch.objects.create(title="curl", os_type=OSType.LINUX, team=[1])
    BaselineRequirement.objects.create(baseline=baseline, patch=patch_a)
    BaselineRequirement.objects.create(baseline=baseline, patch=patch_b)
    HostBaselineBinding.objects.create(target=host_a, baseline=baseline)
    HostBaselineBinding.objects.create(target=host_b, baseline=baseline)
    request = request_factory.post("/")
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"
    mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")

    task = create_remediation_task(
        request,
        [
            {"host_id": host_a.id, "patch_id": patch_a.id},
            {"host_id": host_b.id, "patch_id": patch_b.id},
        ],
        {"execution_mode": "now"},
    )

    assert task.name == "一键治理 · 2台 · 2项"
    assert task.risk_snapshot == [
        {
            "id": f"{host_a.id}:{patch_a.id}:{baseline.id}",
            "host_id": host_a.id,
            "host_name": "host-a",
            "host_ip": "10.0.0.1",
            "patch_id": patch_a.id,
            "patch_name": "openssl",
            "baseline_id": baseline.id,
            "baseline_name": "Linux 基线",
        },
        {
            "id": f"{host_b.id}:{patch_b.id}:{baseline.id}",
            "host_id": host_b.id,
            "host_name": "host-b",
            "host_ip": "10.0.0.2",
            "patch_id": patch_b.id,
            "patch_name": "curl",
            "baseline_id": baseline.id,
            "baseline_name": "Linux 基线",
        },
    ]


@pytest.mark.django_db
def test_install_dispatches_only_patches_selected_for_current_host(mocker):
    host = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    task = GovernanceTask.objects.create(
        name="一键治理 · 2台 · 2项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[host.id],
        patch_list=[101, 202],
        risk_snapshot=[
            {"id": f"{host.id}:101:1", "host_id": host.id, "patch_id": 101},
            {"id": "999:202:1", "host_id": 999, "patch_id": 202},
        ],
        team=[1],
    )
    GovernanceTaskHost.objects.create(task=task, target_id=host.id, target_name=host.name, stage="waiting")
    execute_install = mocker.patch("apps.patch_mgmt.services.patch_execution_service._execute_install")

    run_governance_host(task, host.id)

    assert execute_install.call_args.args[2] == [101]


@pytest.mark.django_db
def test_baseline_assess_creates_one_hidden_parallel_task_for_all_bound_hosts(su_client, mocker):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    trigger = mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")
    baseline = PatchBaseline.objects.create(name="生产基线", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    host_a = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    host_b = PatchTarget.objects.create(name="host-b", ip="10.0.0.2", os_type=OSType.LINUX, team=[1])
    binding_a = HostBaselineBinding.objects.create(target=host_a, baseline=baseline)
    binding_b = HostBaselineBinding.objects.create(target=host_b, baseline=baseline)

    response = su_client.post(f"{BASELINE_URL}{baseline.id}/assess/", format="json")

    assert response.status_code == status.HTTP_201_CREATED
    task = GovernanceTask.objects.get(pk=response.data["task_id"])
    assert task.task_type == GovernanceTaskType.ASSESS
    assert task.name == "评估 · 生产基线 · 2台"
    assert task.target_list == [host_a.id, host_b.id]
    assert task.risk_snapshot == [{
        "baseline_id": baseline.id,
        "baseline_name": "生产基线",
        "baseline_updated_at": baseline.updated_at.isoformat(),
        "requirements_signature": f"{requirement.id}:{patch.id}:{requirement.updated_at.isoformat()}",
        "bindings_signature": f"{binding_a.id}:{host_a.id}|{binding_b.id}:{host_b.id}",
        "requirement_ids": [requirement.id],
        "patch_ids": [patch.id],
        "targets": [
            {"binding_id": binding_a.id, "target_id": host_a.id, "target_name": "host-a"},
            {"binding_id": binding_b.id, "target_id": host_b.id, "target_name": "host-b"},
        ],
    }]
    assert set(task.host_results.values_list("target_id", flat=True)) == {host_a.id, host_b.id}
    assert set(
        HostBaselineBinding.objects.filter(pk__in=[binding_a.id, binding_b.id]).values_list(
            "compliance_status", flat=True
        )
    ) == {"evaluating"}
    trigger.assert_called_once_with(task.id)


@pytest.mark.django_db
def test_saving_unchanged_baseline_bindings_does_not_cancel_active_assessment(
    su_client, mocker
):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    baseline = PatchBaseline.objects.create(
        name="生产基线", os_type=OSType.LINUX, team=[1]
    )
    target = PatchTarget.objects.create(
        name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    task = GovernanceTask.objects.create(
        name="评估 · 生产基线 · 1台",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        risk_snapshot=[{"baseline_id": baseline.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        stage="scanning",
    )

    response = su_client.post(
        f"{BASELINE_URL}{baseline.id}/bind_hosts/",
        {"target_ids": [target.id]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.RUNNING
    assert task.host_results.get(target_id=target.id).stage == "scanning"


@pytest.mark.django_db
def test_baseline_assess_returns_structured_conflict_on_atomic_host_race(su_client, mocker):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    baseline = PatchBaseline.objects.create(
        name="生产基线", os_type=OSType.LINUX, team=[1]
    )
    target = PatchTarget.objects.create(
        name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    mocker.patch(
        "apps.patch_mgmt.services.governance_service.create_assess_task",
        side_effect=HostBusyError([target.id]),
    )

    response = su_client.post(f"{BASELINE_URL}{baseline.id}/assess/", format="json")

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data == {
        "code": "host_busy",
        "detail": f"以下主机正在执行补丁任务: [{target.id}]",
        "target_ids": [target.id],
    }


@pytest.mark.django_db
def test_retry_creates_internal_attempt_under_same_visible_root(request_factory, authenticated_user, mocker):
    root = GovernanceTask.objects.create(
        name="治理 · host-a · 1项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.FAILED,
        target_list=[10],
        patch_list=[20],
        risk_snapshot=[{"id": "10:20:30", "host_id": 10, "patch_id": 20}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root,
        target_id=10,
        target_name="host-a",
        stage="failed",
        can_retry=True,
    )
    PatchTarget.objects.create(id=10, name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    request = request_factory.post("/")
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"
    trigger = mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")

    attempt = create_retry_task(request, root, 10)

    assert attempt.parent_task_id == root.id
    assert attempt.risk_snapshot == root.risk_snapshot
    assert GovernanceTask.objects.filter(parent_task__isnull=True).values_list("id", flat=True).get() == root.id
    root.refresh_from_db()
    assert root.name == "治理 · host-a · 1项"
    trigger.assert_called_once_with(attempt.id)


@pytest.mark.django_db
def test_unmet_validation_can_retry_inside_same_visible_root(
    request_factory, authenticated_user, mocker
):
    target = PatchTarget.objects.create(
        name="host-a", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    binding = HostBaselineBinding.objects.create(
        target=target,
        baseline=baseline,
        compliance_status="non_compliant",
    )
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=False,
        reason="安装后仍未满足",
        evaluated_at="2026-07-23T00:00:00Z",
    )
    root = GovernanceTask.objects.create(
        name="治理 · host-a · 1项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[patch.id],
        risk_snapshot=[{
            "id": f"{target.id}:{patch.id}:{baseline.id}",
            "host_id": target.id,
            "host_name": target.name,
            "patch_id": patch.id,
        }],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root,
        target_id=target.id,
        target_name=target.name,
        stage="completed",
        can_retry=False,
    )
    verify = GovernanceTask.objects.create(
        name="自动验证",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.COMPLETED,
        parent_task=root,
        target_list=[target.id],
        patch_list=[patch.id],
        risk_snapshot=root.risk_snapshot,
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=verify,
        target_id=target.id,
        target_name=target.name,
        stage="completed",
        can_retry=False,
    )
    request = request_factory.post("/")
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"
    trigger = mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")

    attempt = create_retry_task(request, root, target.id)

    assert attempt.parent_task_id == root.id
    assert attempt.patch_list == [patch.id]
    assert attempt.risk_snapshot == root.risk_snapshot
    trigger.assert_called_once_with(attempt.id)


@pytest.mark.django_db
def test_risk_summary_query_count_does_not_grow_per_patch():
    risk_snapshot = [
        {
            "id": f"10:{patch_id}:30",
            "host_id": 10,
            "host_name": "host-a",
            "patch_id": patch_id,
            "patch_name": f"patch-{patch_id}",
        }
        for patch_id in range(1, 31)
    ]
    root = GovernanceTask.objects.create(
        name="治理 · host-a · 30项",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[10],
        patch_list=list(range(1, 31)),
        risk_snapshot=risk_snapshot,
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=root,
        target_id=10,
        target_name="host-a",
        stage="completed",
    )
    verify = GovernanceTask.objects.create(
        name="自动验证",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.COMPLETED,
        parent_task=root,
        target_list=[10],
        patch_list=list(range(1, 31)),
        risk_snapshot=risk_snapshot,
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=verify,
        target_id=10,
        target_name="host-a",
        stage="completed",
    )

    with CaptureQueriesContext(connection) as queries:
        summaries = build_risk_item_summaries(root)

    assert len(summaries) == 30
    assert len(queries) <= 5
