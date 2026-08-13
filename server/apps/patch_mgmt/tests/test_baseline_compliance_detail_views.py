"""基线合规详情公开接口契约。"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
    RequirementAssessmentStatus,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    HostBaselineBinding,
    HostComplianceSnapshot,
    GovernanceTask,
    GovernanceTaskHost,
    Patch,
    PatchBaseline,
    PatchTarget,
    WindowsPatchDetail,
)


BASE = "/api/v1/patch_mgmt/api"


def _windows_requirement(baseline, kb_number):
    patch = Patch.objects.create(
        title=f"{kb_number} security update",
        os_type=OSType.WINDOWS,
        severity="important",
        team=[1],
    )
    WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number=kb_number,
        product_list=["Windows 10"],
        architectures=["x64"],
    )
    return BaselineRequirement.objects.create(baseline=baseline, patch=patch)


@pytest.mark.django_db
class TestBaselineComplianceDetailApi:
    def test_objects_endpoint_returns_all_hosts_without_detail_payload(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        _windows_requirement(baseline, "KB6000200")
        targets = [
            PatchTarget.objects.create(
                name=f"web-{index:02d}",
                ip=f"10.0.0.{index}",
                os_type=OSType.WINDOWS,
                team=[1],
            )
            for index in range(1, 4)
        ]
        for target in targets:
            HostBaselineBinding.objects.create(target=target, baseline=baseline)

        response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_objects/",
            {"perspective": "host", "page_size": -1},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["perspective"] == "host"
        assert response.data["count"] == 3
        assert [item["id"] for item in response.data["items"]] == [
            target.id for target in targets
        ]
        assert "details" not in response.data
        assert "selected" not in response.data

    def test_details_endpoint_only_returns_selected_host_paged_details(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        requirements = [
            _windows_requirement(baseline, f"KB600021{index}")
            for index in range(3)
        ]
        target = PatchTarget.objects.create(
            name="web-01",
            ip="10.0.1.20",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        HostBaselineBinding.objects.create(target=target, baseline=baseline)

        response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {
                "perspective": "host",
                "selected_id": target.id,
                "page": 2,
                "page_size": 2,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["perspective"] == "host"
        assert response.data["selected"]["id"] == target.id
        assert response.data["details"]["count"] == 3
        assert response.data["details"]["page"] == 2
        assert response.data["details"]["page_size"] == 2
        assert (
            response.data["details"]["items"][0]["requirement_id"]
            == requirements[2].id
        )
        assert "objects" not in response.data

    def test_details_search_does_not_filter_the_baseline_lookup(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Linux production",
            os_type=OSType.LINUX,
            team=[1],
        )
        patch = Patch.objects.create(
            title="aide integrity checker",
            os_type=OSType.LINUX,
            severity="medium",
            team=[1],
        )
        requirement = BaselineRequirement.objects.create(
            baseline=baseline,
            patch=patch,
        )
        target = PatchTarget.objects.create(
            name="linux-01",
            ip="10.0.1.30",
            os_type=OSType.LINUX,
            team=[1],
        )
        HostBaselineBinding.objects.create(target=target, baseline=baseline)

        response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {
                "perspective": "host",
                "selected_id": target.id,
                "search": "aide",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["selected"]["id"] == target.id
        assert response.data["details"]["count"] == 1
        assert response.data["details"]["items"][0]["requirement_id"] == requirement.id

    def test_split_endpoints_reject_invalid_or_missing_pagination_inputs(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )

        objects_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_objects/",
            {"page_size": 101},
        )
        details_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {"perspective": "host", "page_size": 101},
        )

        assert objects_response.status_code == status.HTTP_400_BAD_REQUEST
        assert details_response.status_code == status.HTTP_400_BAD_REQUEST

    def test_host_perspective_returns_host_list_and_all_patch_results(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        satisfied_requirement = _windows_requirement(baseline, "KB6000201")
        pending_requirement = _windows_requirement(baseline, "KB6000202")
        target = PatchTarget.objects.create(
            name="web-01",
            ip="10.0.0.20",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        evaluated_at = timezone.now() - timedelta(minutes=5)
        binding = HostBaselineBinding.objects.create(
            target=target,
            baseline=baseline,
            compliance_status=ComplianceStatus.NON_COMPLIANT,
            missing_count=1,
            last_evaluated_at=evaluated_at,
        )
        HostComplianceSnapshot.objects.create(
            binding=binding,
            requirement=satisfied_requirement,
            satisfied=True,
            status=RequirementAssessmentStatus.SATISFIED,
            evidence={"installed_kb": "KB6000201"},
            reason="KB is installed",
            evaluated_at=evaluated_at,
        )

        objects_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_objects/",
            {"perspective": "host", "page_size": -1},
        )
        details_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {"perspective": "host", "selected_id": target.id},
        )

        assert objects_response.status_code == status.HTTP_200_OK
        assert details_response.status_code == status.HTTP_200_OK
        assert objects_response.data["baseline"] == {
            "id": baseline.id,
            "name": baseline.name,
            "os_type": OSType.WINDOWS,
        }
        assert objects_response.data["perspective"] == "host"
        assert objects_response.data["count"] == 1
        assert objects_response.data["items"][0]["id"] == target.id
        assert objects_response.data["items"][0]["distribution"] == [
            {"status": "satisfied", "count": 1},
            {"status": "unknown", "count": 1},
        ]
        assert details_response.data["selected"]["id"] == target.id
        assert details_response.data["details"]["count"] == 2
        assert [
            item["requirement_id"]
            for item in details_response.data["details"]["items"]
        ] == [
            satisfied_requirement.id,
            pending_requirement.id,
        ]
        assert details_response.data["details"]["items"][0]["status"] == "satisfied"
        assert (
            details_response.data["details"]["items"][0]["status_scope"]
            == "requirement"
        )
        assert details_response.data["details"]["items"][0]["evidence"] == {
            "installed_kb": "KB6000201"
        }
        assert details_response.data["details"]["items"][1]["status"] == "unknown"
        assert details_response.data["details"]["items"][1]["status_scope"] == "host"
        assert (
            details_response.data["details"]["items"][1]["reason"]
            == "No current valid assessment snapshot; assessment data is incomplete"
        )
        assert (
            details_response.data["details"]["items"][1]["evaluated_at"]
            == evaluated_at.isoformat().replace("+00:00", "Z")
        )

    def test_patch_perspective_returns_patch_list_and_all_host_results(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        requirement = _windows_requirement(baseline, "KB6000210")
        satisfied_target = PatchTarget.objects.create(
            name="api-01",
            ip="10.0.1.20",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        missing_target = PatchTarget.objects.create(
            name="web-01",
            ip="10.0.1.21",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        evaluated_at = timezone.now() - timedelta(minutes=3)
        satisfied_binding = HostBaselineBinding.objects.create(
            target=satisfied_target,
            baseline=baseline,
            compliance_status=ComplianceStatus.COMPLIANT,
            last_evaluated_at=evaluated_at,
        )
        missing_binding = HostBaselineBinding.objects.create(
            target=missing_target,
            baseline=baseline,
            compliance_status=ComplianceStatus.NON_COMPLIANT,
            missing_count=1,
            last_evaluated_at=evaluated_at,
        )
        HostComplianceSnapshot.objects.create(
            binding=satisfied_binding,
            requirement=requirement,
            satisfied=True,
            status=RequirementAssessmentStatus.SATISFIED,
            reason="installed",
            evaluated_at=evaluated_at,
        )
        HostComplianceSnapshot.objects.create(
            binding=missing_binding,
            requirement=requirement,
            satisfied=False,
            status=RequirementAssessmentStatus.MISSING,
            evidence={"available_kb": "KB6000210"},
            reason="update is applicable and missing",
            evaluated_at=evaluated_at,
        )

        objects_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_objects/",
            {"perspective": "patch", "page_size": -1},
        )
        details_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {"perspective": "patch", "selected_id": requirement.id},
        )

        assert objects_response.status_code == status.HTTP_200_OK
        assert details_response.status_code == status.HTTP_200_OK
        assert objects_response.data["perspective"] == "patch"
        assert objects_response.data["count"] == 1
        assert objects_response.data["items"][0]["id"] == requirement.id
        assert objects_response.data["items"][0]["distribution"] == [
            {"status": "satisfied", "count": 1},
            {"status": "missing", "count": 1},
        ]
        assert details_response.data["selected"]["identifier"] == "KB6000210"
        assert details_response.data["details"]["count"] == 2
        assert [
            item["target_id"]
            for item in details_response.data["details"]["items"]
        ] == [
            satisfied_target.id,
            missing_target.id,
        ]
        assert details_response.data["details"]["items"][1]["status"] == "missing"
        assert (
            details_response.data["details"]["items"][1]["status_scope"]
            == "requirement"
        )
        assert details_response.data["details"]["items"][1]["evidence"] == {
            "available_kb": "KB6000210"
        }

    def test_host_failure_uses_real_task_reason_without_faking_patch_snapshot(
        self, su_client
    ):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        requirement = _windows_requirement(baseline, "KB6000220")
        target = PatchTarget.objects.create(
            name="failed-host",
            ip="10.0.2.20",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        HostBaselineBinding.objects.create(
            target=target,
            baseline=baseline,
            compliance_status=ComplianceStatus.FAILED,
            last_evaluated_at=timezone.now(),
        )
        task = GovernanceTask.objects.create(
            name="failed assessment",
            task_type=GovernanceTaskType.ASSESS,
            status=GovernanceTaskStatus.FAILED,
            target_list=[target.id],
            risk_snapshot=[{"baseline_id": baseline.id, "host_id": target.id}],
            team=[1],
        )
        failed_at = timezone.now() - timedelta(minutes=1)
        task_host = GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="failed",
            error_code="executor_unavailable",
            failed_stage="assess",
            reason="nats: no responders available for request",
        )
        GovernanceTaskHost.objects.filter(id=task_host.id).update(updated_at=failed_at)

        response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {"perspective": "host", "selected_id": target.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["selected"]["failure"] == {
            "reason": "nats: no responders available for request",
            "error_code": "executor_unavailable",
            "failed_stage": "assess",
        }
        item = response.data["details"]["items"][0]
        assert item["requirement_id"] == requirement.id
        assert item["status"] == "failed"
        assert item["status_scope"] == "host"
        assert item["reason"] == "nats: no responders available for request"
        assert item["evidence"] == {}
        assert item["evaluated_at"] == failed_at.isoformat().replace("+00:00", "Z")

        patch_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {"perspective": "patch", "selected_id": requirement.id},
        )
        patch_item = patch_response.data["details"]["items"][0]
        assert patch_item["status"] == "failed"
        assert patch_item["status_scope"] == "host"
        assert patch_item["reason"] == "nats: no responders available for request"
        assert patch_item["failure"] == {
            "reason": "nats: no responders available for request",
            "error_code": "executor_unavailable",
            "failed_stage": "assess",
        }
        assert (
            patch_item["evaluated_at"]
            == failed_at.isoformat().replace("+00:00", "Z")
        )

    def test_patch_perspective_filters_projected_host_scope_status(self, su_client):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        requirement = _windows_requirement(baseline, "KB6000225")
        evaluating_target = PatchTarget.objects.create(
            name="evaluating-host",
            ip="10.0.2.25",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        pending_target = PatchTarget.objects.create(
            name="pending-host",
            ip="10.0.2.26",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        for target in (evaluating_target, pending_target):
            HostBaselineBinding.objects.create(target=target, baseline=baseline)
        task = GovernanceTask.objects.create(
            name="active assessment",
            task_type=GovernanceTaskType.ASSESS,
            status=GovernanceTaskStatus.RUNNING,
            target_list=[evaluating_target.id],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=evaluating_target.id,
            target_name=evaluating_target.name,
            target_ip=evaluating_target.ip,
            stage="scanning",
        )

        response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {
                "perspective": "patch",
                "selected_id": requirement.id,
                "status": "evaluating",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["details"]["count"] == 1
        assert response.data["details"]["items"][0]["target_id"] == evaluating_target.id
        assert response.data["details"]["items"][0]["status"] == "evaluating"
        assert response.data["details"]["items"][0]["status_scope"] == "host"

    def test_patch_perspective_filters_missing_snapshot_by_effective_fallback_status(
        self, su_client
    ):
        baseline = PatchBaseline.objects.create(
            name="Windows production",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        requirement = _windows_requirement(baseline, "KB6000226")
        evaluated_at = timezone.now() - timedelta(minutes=5)
        unknown_target = PatchTarget.objects.create(
            name="incomplete-host",
            ip="10.0.2.27",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        pending_target = PatchTarget.objects.create(
            name="new-host",
            ip="10.0.2.28",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        HostBaselineBinding.objects.create(
            target=unknown_target,
            baseline=baseline,
            compliance_status=ComplianceStatus.NON_COMPLIANT,
            last_evaluated_at=evaluated_at,
        )
        HostBaselineBinding.objects.create(target=pending_target, baseline=baseline)

        unknown_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {
                "perspective": "patch",
                "selected_id": requirement.id,
                "status": "unknown",
            },
        )
        pending_response = su_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {
                "perspective": "patch",
                "selected_id": requirement.id,
                "status": "pending",
            },
        )

        assert [
            item["target_id"]
            for item in unknown_response.data["details"]["items"]
        ] == [unknown_target.id]
        assert [
            item["target_id"]
            for item in pending_response.data["details"]["items"]
        ] == [pending_target.id]

    def test_only_returns_targets_visible_to_current_user(
        self, api_client, authenticated_user, mocker
    ):
        baseline = PatchBaseline.objects.create(
            name="Shared Windows baseline",
            os_type=OSType.WINDOWS,
            team=[2],
        )
        _windows_requirement(baseline, "KB6000230")
        visible = PatchTarget.objects.create(
            name="visible",
            ip="10.0.3.20",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        hidden = PatchTarget.objects.create(
            name="hidden",
            ip="10.0.3.21",
            os_type=OSType.WINDOWS,
            team=[2],
        )
        for target in (visible, hidden):
            HostBaselineBinding.objects.create(target=target, baseline=baseline)

        authenticated_user.is_superuser = False
        authenticated_user.roles = []
        authenticated_user.permission = {"patch": {"patch_baseline-View"}}
        api_client.cookies["current_team"] = "1"
        mocker.patch(
            "apps.core.utils.viewset_utils.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )

        response = api_client.get(
            f"{BASE}/baseline/{baseline.id}/compliance_matrix_details/",
            {"perspective": "patch", "selected_id": baseline.requirements.get().id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["details"]["count"] == 1
        assert response.data["details"]["items"][0]["target_id"] == visible.id
