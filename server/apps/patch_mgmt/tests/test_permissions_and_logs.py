"""补丁管理权限集成与操作日志测试。"""

from unittest.mock import MagicMock

import pytest
from rest_framework import status

from apps.patch_mgmt.utils.operation_log import (
    log_governance_task_cancelled,
    log_install_task_cancelled,
    log_install_task_created,
    log_patch_created,
    log_patch_deleted,
    log_patch_updated,
    log_reboot_triggered,
    log_scan_task_cancelled,
    log_scan_task_created,
    log_source_changed,
    log_target_created,
    log_target_deleted,
    log_target_updated,
    log_windows_version_changed,
)
from apps.system_mgmt.models.operation_log import OperationLog


_BASE = "/api/v1/patch_mgmt"


def _permission_client(api_client, authenticated_user, permissions):
    authenticated_user.is_superuser = False
    authenticated_user.roles = []
    authenticated_user.permission = {"patch": set(permissions)}
    api_client.cookies["current_team"] = "1"
    return api_client


def _team_rule(mocker, *, team=1):
    return mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [team], "instance": []},
    )


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_request(username="testuser", domain="test.com"):
    """构造最小化 mock request，满足 log_operation 的字段访问需求。"""
    req = MagicMock()
    req.user.username = username
    req.user.domain = domain
    # ipware.get_client_ip 使用 META["REMOTE_ADDR"]
    req.META = {"REMOTE_ADDR": "127.0.0.1"}
    return req


@pytest.mark.django_db
class TestPatchPermissionApiBoundaries:
    def test_patch_source_view_permission_uses_patch_application_id(
        self, api_client, authenticated_user, mocker
    ):
        from apps.patch_mgmt.constants import PatchSourceType
        from apps.patch_mgmt.models import PatchSource

        PatchSource.objects.create(
            name="team-source",
            source_type=PatchSourceType.APT_REPO,
            url="https://archive.example.com/ubuntu",
            team=[1],
        )
        client = _permission_client(api_client, authenticated_user, {"patch_source-View"})
        _team_rule(mocker)

        response = client.get(f"{_BASE}/api/patch_source/")

        assert response.status_code == status.HTTP_200_OK

    def test_target_update_requires_edit_operation_permission(
        self, api_client, authenticated_user, mocker
    ):
        from apps.patch_mgmt.models import PatchTarget

        target = PatchTarget.objects.create(name="target", ip="10.0.0.10", team=[1])
        client = _permission_client(api_client, authenticated_user, {"patch_target-View"})
        _team_rule(mocker)

        response = client.patch(
            f"{_BASE}/api/patch_target/{target.id}/",
            {"name": "forbidden-update"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        target.refresh_from_db()
        assert target.name == "target"

    def test_baseline_edit_permission_can_add_requirement(
        self, api_client, authenticated_user, mocker
    ):
        from apps.patch_mgmt.constants import OSType
        from apps.patch_mgmt.models import Patch, PatchBaseline

        baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
        patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
        client = _permission_client(api_client, authenticated_user, {"patch_baseline-Edit"})
        _team_rule(mocker)

        response = client.post(
            f"{_BASE}/api/baseline/{baseline.id}/requirements/",
            {"patch_ids": [patch.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert baseline.requirements.filter(patch=patch).exists()

    def test_baseline_view_permission_cannot_add_requirement(
        self, api_client, authenticated_user, mocker
    ):
        from apps.patch_mgmt.constants import OSType
        from apps.patch_mgmt.models import Patch, PatchBaseline

        baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
        patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
        client = _permission_client(api_client, authenticated_user, {"patch_baseline-View"})
        _team_rule(mocker)

        response = client.post(
            f"{_BASE}/api/baseline/{baseline.id}/requirements/",
            {"patch_ids": [patch.id]},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not baseline.requirements.exists()

    def test_risk_list_only_contains_targets_in_current_team_scope(
        self, api_client, authenticated_user, mocker
    ):
        from apps.patch_mgmt.constants import ComplianceStatus, OSType
        from apps.patch_mgmt.models import (
            BaselineRequirement,
            HostBaselineBinding,
            Patch,
            PatchBaseline,
            PatchTarget,
        )

        baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
        patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)
        allowed = PatchTarget.objects.create(name="allowed", ip="10.0.0.21", team=[1])
        denied = PatchTarget.objects.create(name="denied", ip="10.0.0.22", team=[2])
        for target in (allowed, denied):
            HostBaselineBinding.objects.create(
                target=target,
                baseline=baseline,
                compliance_status=ComplianceStatus.NON_COMPLIANT,
            )
        client = _permission_client(api_client, authenticated_user, {"patch_risk-View"})

        mocker.patch(
            "apps.core.utils.viewset_utils.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )

        response = client.get(f"{_BASE}/api/risk/?view=host")

        assert response.status_code == status.HTTP_200_OK
        assert [item["key"] for item in response.data["results"]] == [f"h-{allowed.id}"]

    def test_dashboard_counts_only_targets_in_current_team_scope(
        self, api_client, authenticated_user, mocker
    ):
        from apps.patch_mgmt.models import PatchTarget

        allowed = PatchTarget.objects.create(name="allowed", ip="10.0.0.31", team=[1])
        PatchTarget.objects.create(name="denied", ip="10.0.0.32", team=[2])
        client = _permission_client(api_client, authenticated_user, {"patch_dashboard-View"})

        mocker.patch(
            "apps.core.utils.viewset_utils.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )

        response = client.get(f"{_BASE}/api/dashboard/stats/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["target_total"] == 1


# ── Section 2: operation_log writes ──────────────────────────────────────────


@pytest.mark.django_db
class TestOperationLogWrites:
    """验证 13 个 spec 操作类别都能写入 OperationLog，且 app='patch'。"""

    def test_log_patch_created(self):
        log_patch_created(_mock_request(), "KB5001234")
        assert OperationLog.objects.filter(
            app="patch", action_type="create", summary__icontains="KB5001234"
        ).exists()

    def test_log_patch_updated(self):
        log_patch_updated(_mock_request(), "KB5001234")
        assert OperationLog.objects.filter(
            app="patch", action_type="update", summary__icontains="KB5001234"
        ).exists()

    def test_log_patch_deleted(self):
        log_patch_deleted(_mock_request(), "KB5001234")
        assert OperationLog.objects.filter(
            app="patch", action_type="delete", summary__icontains="KB5001234"
        ).exists()

    def test_log_target_created(self):
        log_target_created(_mock_request(), "web-server-01")
        assert OperationLog.objects.filter(
            app="patch", action_type="create", summary__icontains="web-server-01"
        ).exists()

    def test_log_target_updated(self):
        log_target_updated(_mock_request(), "web-server-01")
        assert OperationLog.objects.filter(
            app="patch", action_type="update", summary__icontains="web-server-01"
        ).exists()

    def test_log_target_deleted(self):
        log_target_deleted(_mock_request(), "web-server-01")
        assert OperationLog.objects.filter(
            app="patch", action_type="delete", summary__icontains="web-server-01"
        ).exists()

    def test_log_scan_task_created(self):
        log_scan_task_created(_mock_request(), "scan-2026-06")
        assert OperationLog.objects.filter(
            app="patch", action_type="execute", summary__icontains="scan-2026-06"
        ).exists()

    def test_log_scan_task_cancelled(self):
        log_scan_task_cancelled(_mock_request(), "scan-2026-06")
        assert OperationLog.objects.filter(
            app="patch", action_type="execute", summary__icontains="scan-2026-06"
        ).exists()

    def test_log_install_task_created(self):
        log_install_task_created(_mock_request(), "install-2026-06")
        assert OperationLog.objects.filter(
            app="patch", action_type="execute", summary__icontains="install-2026-06"
        ).exists()

    def test_log_install_task_cancelled(self):
        log_install_task_cancelled(_mock_request(), "install-2026-06")
        assert OperationLog.objects.filter(
            app="patch", action_type="execute", summary__icontains="install-2026-06"
        ).exists()

    def test_log_governance_task_cancelled_includes_reason(self):
        log_governance_task_cancelled(_mock_request(), "install-2026-06", "维护窗口调整")
        operation = OperationLog.objects.get(
            app="patch",
            action_type="execute",
            summary__icontains="install-2026-06",
        )
        assert "维护窗口调整" in operation.summary

    def test_log_reboot_triggered(self):
        log_reboot_triggered(_mock_request(), "install-2026-06")
        assert OperationLog.objects.filter(
            app="patch", action_type="execute", summary__icontains="install-2026-06"
        ).exists()

    def test_log_source_changed_create(self):
        log_source_changed(_mock_request(), "create", "wsus-1")
        assert OperationLog.objects.filter(
            app="patch", action_type="create", summary__icontains="wsus-1"
        ).exists()

    def test_log_windows_version_changed_update(self):
        log_windows_version_changed(_mock_request(), "update", "Windows 10 22H2")
        assert OperationLog.objects.filter(
            app="patch", action_type="update", summary__icontains="Windows 10 22H2"
        ).exists()

    def test_all_spec_logs_use_patch_app_name(self):
        """全部 spec 操作的 app 字段必须为 'patch'，不得写错模块名。"""
        sentinel = "sentinel-todo10"
        log_patch_created(_mock_request(), sentinel)
        log_target_created(_mock_request(), sentinel)
        log_scan_task_created(_mock_request(), sentinel)
        log_install_task_created(_mock_request(), sentinel)
        log_reboot_triggered(_mock_request(), sentinel)
        count = OperationLog.objects.filter(app="patch", summary__icontains=sentinel).count()
        assert count == 5

    def test_log_operation_returns_none_on_missing_username_gracefully(self):
        """log_operation 失败时静默返回 None，不抛异常，不阻断主业务。"""
        bad_req = MagicMock()
        bad_req.user.username = None  # 触发 OperationLog create 异常
        bad_req.META = {}
        # 任何调用都不应抛出
        result = log_patch_created(bad_req, "any-patch")
        # 静默失败：result 为 None（log_operation 内部捕获）
        assert result is None
