"""补丁管理以 PatchTarget 为唯一数据权限根的公开 API 契约。"""

import pytest
from rest_framework import status

from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    Patch,
    PatchBaseline,
    PatchSource,
    PatchTarget,
)


BASE = "/api/v1/patch_mgmt/api"


def _client(api_client, user, permissions):
    user.is_superuser = False
    user.roles = []
    user.permission = {"patch": set(permissions)}
    api_client.cookies["current_team"] = "1"
    return api_client


def _target_rules(mocker, *, visible_team=1, instances=None):
    def rules(_user, _team, _app, module, _children):
        if module != "patch_target":
            return {"team": [], "instance": []}
        return {"team": [visible_team], "instance": instances or []}

    return mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules", side_effect=rules
    )


@pytest.mark.django_db
class TestTargetRootedReadScope:
    def test_patch_source_and_baseline_are_global_shared(
        self, api_client, authenticated_user, mocker
    ):
        patch = Patch.objects.create(
            title="cross-team patch", os_type=OSType.LINUX, team=[2]
        )
        source = PatchSource.objects.create(
            name="cross-team source", source_type="apt", team=[2]
        )
        baseline = PatchBaseline.objects.create(
            name="cross-team baseline", os_type=OSType.LINUX, team=[2]
        )
        client = _client(
            api_client,
            authenticated_user,
            {"patch-View", "patch_source-View", "patch_baseline-View"},
        )
        _target_rules(mocker)

        patch_response = client.get(f"{BASE}/patch/")
        source_response = client.get(f"{BASE}/patch_source/")
        baseline_response = client.get(f"{BASE}/baseline/")

        assert patch_response.status_code == status.HTTP_200_OK
        assert source_response.status_code == status.HTTP_200_OK
        assert baseline_response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in patch_response.json()["data"]] == [patch.id]
        assert [row["id"] for row in source_response.json()["data"]] == [source.id]
        assert [row["id"] for row in baseline_response.json()["data"]] == [
            baseline.id
        ]
        assert patch_response.json()["data"][0]["permission"] == [
            "View",
            "Operate",
        ]

    def test_risk_scope_depends_only_on_visible_target(
        self, api_client, authenticated_user, mocker
    ):
        baseline = PatchBaseline.objects.create(
            name="shared baseline", os_type=OSType.LINUX, team=[2]
        )
        patch = Patch.objects.create(
            title="shared patch", os_type=OSType.LINUX, team=[2]
        )
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)
        visible = PatchTarget.objects.create(
            name="visible", ip="10.0.0.1", team=[1]
        )
        hidden = PatchTarget.objects.create(
            name="hidden", ip="10.0.0.2", team=[2]
        )
        for target in (visible, hidden):
            HostBaselineBinding.objects.create(
                target=target,
                baseline=baseline,
                compliance_status=ComplianceStatus.NON_COMPLIANT,
            )
        client = _client(api_client, authenticated_user, {"patch_risk-View"})
        _target_rules(mocker)

        response = client.get(f"{BASE}/risk/?view=host")

        assert response.status_code == status.HTTP_200_OK
        assert [row["key"] for row in response.data["results"]] == [
            f"h-{visible.id}"
        ]

    def test_execution_record_is_hidden_or_projected_by_visible_hosts(
        self, api_client, authenticated_user, mocker
    ):
        visible = PatchTarget.objects.create(
            name="visible", ip="10.0.0.11", team=[1]
        )
        hidden = PatchTarget.objects.create(
            name="hidden", ip="10.0.0.12", team=[2]
        )
        mixed = GovernanceTask.objects.create(
            name="mixed",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.RUNNING,
            target_list=[visible.id, hidden.id],
            risk_snapshot=[
                {"id": f"{visible.id}:1:1", "host_id": visible.id, "patch_id": 1},
                {"id": f"{hidden.id}:1:1", "host_id": hidden.id, "patch_id": 1},
            ],
            team=[2],
        )
        hidden_only = GovernanceTask.objects.create(
            name="hidden-only",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.RUNNING,
            target_list=[hidden.id],
            team=[2],
        )
        GovernanceTaskHost.objects.create(
            task=mixed, target_id=visible.id, target_name=visible.name, stage="completed"
        )
        GovernanceTaskHost.objects.create(
            task=mixed, target_id=hidden.id, target_name=hidden.name, stage="waiting"
        )
        GovernanceTaskHost.objects.create(
            task=hidden_only,
            target_id=hidden.id,
            target_name=hidden.name,
            stage="waiting",
        )
        client = _client(api_client, authenticated_user, {"patch_governance-View"})
        _target_rules(mocker)

        response = client.get(f"{BASE}/governance/")
        detail = client.get(f"{BASE}/governance/{mixed.id}/")
        hidden_detail = client.get(f"{BASE}/governance/{hidden_only.id}/")

        assert response.status_code == status.HTTP_200_OK
        rows = (
            response.data.get("results", response.data)
            if isinstance(response.data, dict)
            else response.data
        )
        assert [row["id"] for row in rows] == [mixed.id]
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["target_list"] == [visible.id]
        assert detail.data["host_count"] == 1
        assert [row["target_id"] for row in detail.data["host_results"]] == [
            visible.id
        ]
        assert [row["host_id"] for row in detail.data["risk_items"]] == [
            visible.id
        ]
        assert hidden_detail.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTargetRootedOperationScope:
    def test_explicit_binding_rejects_entire_request_when_any_target_is_denied(
        self, api_client, authenticated_user, mocker
    ):
        baseline = PatchBaseline.objects.create(
            name="shared", os_type=OSType.LINUX, team=[2]
        )
        allowed = PatchTarget.objects.create(
            name="allowed", ip="10.0.1.1", os_type=OSType.LINUX, team=[1]
        )
        denied = PatchTarget.objects.create(
            name="denied", ip="10.0.1.2", os_type=OSType.LINUX, team=[2]
        )
        client = _client(api_client, authenticated_user, {"patch_target-Edit"})
        _target_rules(mocker)

        response = client.post(
            f"{BASE}/baseline/{baseline.id}/bind_hosts/",
            {"target_ids": [allowed.id, denied.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not HostBaselineBinding.objects.exists()

    def test_baseline_assessment_automatically_trims_to_operable_targets(
        self, api_client, authenticated_user, mocker
    ):
        baseline = PatchBaseline.objects.create(
            name="shared", os_type=OSType.LINUX, team=[2]
        )
        patch = Patch.objects.create(
            title="openssl", os_type=OSType.LINUX, team=[2]
        )
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)
        allowed = PatchTarget.objects.create(
            name="allowed", ip="10.0.2.1", os_type=OSType.LINUX, team=[1]
        )
        denied = PatchTarget.objects.create(
            name="denied", ip="10.0.2.2", os_type=OSType.LINUX, team=[2]
        )
        HostBaselineBinding.objects.create(target=allowed, baseline=baseline)
        HostBaselineBinding.objects.create(target=denied, baseline=baseline)
        client = _client(
            api_client, authenticated_user, {"patch_governance-Add"}
        )
        _target_rules(mocker)
        mocker.patch(
            "apps.patch_mgmt.services.governance_service._trigger_async"
        )

        response = client.post(
            f"{BASE}/baseline/{baseline.id}/assess/", format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        task = GovernanceTask.objects.get(pk=response.data["task_id"])
        assert task.target_list == [allowed.id]
        assert list(task.host_results.values_list("target_id", flat=True)) == [
            allowed.id
        ]

    def test_cancel_only_cancels_operable_waiting_hosts(
        self, api_client, authenticated_user, mocker
    ):
        allowed = PatchTarget.objects.create(
            name="allowed", ip="10.0.3.1", os_type=OSType.LINUX, team=[1]
        )
        denied = PatchTarget.objects.create(
            name="denied", ip="10.0.3.2", os_type=OSType.LINUX, team=[2]
        )
        task = GovernanceTask.objects.create(
            name="mixed",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.PENDING,
            target_list=[allowed.id, denied.id],
            team=[2],
        )
        for target in (allowed, denied):
            GovernanceTaskHost.objects.create(
                task=task,
                target_id=target.id,
                target_name=target.name,
                stage="waiting",
            )
        client = _client(
            api_client,
            authenticated_user,
            {"patch_governance-View", "patch_governance-Edit"},
        )
        _target_rules(mocker)

        response = client.post(
            f"{BASE}/governance/{task.id}/cancel/",
            {"reason": "maintenance cancelled"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["cancelled_count"] == 1
        assert response.data["skipped_count"] == 1
        assert task.host_results.get(target_id=allowed.id).stage == "cancelled"
        assert task.host_results.get(target_id=denied.id).stage == "waiting"
        task.refresh_from_db()
        assert task.status == GovernanceTaskStatus.RUNNING
