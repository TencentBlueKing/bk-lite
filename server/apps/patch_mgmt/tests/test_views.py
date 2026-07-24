"""补丁管理 API / View 层集成测试（Todo 9）

测试策略：
  - 所有测试使用 su_client（超管 + current_team=1）穿过鉴权层。
  - 覆盖 HTTP 路由解析、序列化字段、filter、export、自定义 action、错误路径。
  - Celery 任务通过 mocker 隔离 apply_async，防止无 broker 报错。
  - 测试类名包含 View/Api/Export → 全部命中 -k "view or api or export" 过滤器。
"""

import pytest
from rest_framework import status

from apps.patch_mgmt.constants import (
    OSType,
    PatchSourceType,
)
from apps.patch_mgmt.models import (
    Patch,
    PatchSource,
    PatchTarget,
)

# ── URL 常量 ──────────────────────────────────────────────────────────────────

_BASE = "/api/v1/patch_mgmt"

PATCH_SOURCE_URL = f"{_BASE}/api/patch_source/"
PATCH_URL = f"{_BASE}/api/patch/"
PATCH_TARGET_URL = f"{_BASE}/api/patch_target/"
DASHBOARD_STATS_URL = f"{_BASE}/api/dashboard/stats/"


# ── PatchSource ViewSet ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPatchSourceViewApi:
    def test_list_api_returns_200(self, su_client):
        resp = su_client.get(PATCH_SOURCE_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_create_api_succeeds(self, su_client):
        data = {
            "name": "WSUS-Local",
            "source_type": PatchSourceType.WSUS,
            "url": "http://wsus.example.com",
            "team": [1],
        }
        resp = su_client.post(PATCH_SOURCE_URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "WSUS-Local"
        assert resp.data["source_type"] == PatchSourceType.WSUS

    def test_create_api_encrypts_source_password(self, su_client, mocker):
        mocker.patch("apps.patch_mgmt.views.patch_source.PatchSourceViewSet._probe_connectivity")
        resp = su_client.post(
            PATCH_SOURCE_URL,
            {
                "name": "WSUS-Secure",
                "source_type": PatchSourceType.WSUS,
                "url": "http://wsus.example.com",
                "auth_user": "svc-wsus",
                "auth_password": "plain-secret",
                "team": [1],
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        source = PatchSource.objects.get(name="WSUS-Secure")
        assert source.auth_password != "plain-secret"
        assert source.get_auth_password() == "plain-secret"

    def test_retrieve_api_returns_source(self, su_client):
        src = PatchSource.objects.create(
            name="WSUS-01", source_type=PatchSourceType.WSUS, team=[1]
        )
        resp = su_client.get(f"{PATCH_SOURCE_URL}{src.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "WSUS-01"
        assert resp.data["has_auth_password"] is False
        assert "auth_password" not in resp.data

    def test_retrieve_api_only_returns_saved_password_presence(self, su_client):
        from apps.core.mixinx import EncryptMixin

        credentials = {"auth_password": "saved-secret"}
        EncryptMixin.encrypt_field("auth_password", credentials)
        src = PatchSource.objects.create(
            name="WSUS-Secure",
            source_type=PatchSourceType.WSUS,
            auth_password=credentials["auth_password"],
            team=[1],
        )

        resp = su_client.get(f"{PATCH_SOURCE_URL}{src.id}/")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["has_auth_password"] is True
        assert "auth_password" not in resp.data

    def test_unsaved_source_form_can_test_connectivity(self, su_client, mocker):
        probe = mocker.patch(
            "apps.patch_mgmt.views.patch_source.probe_source",
            return_value=mocker.Mock(reachable=True, status_code=200, detail="repo metadata ok"),
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}test_connectivity/",
            {
                "source_type": PatchSourceType.APT_REPO,
                "url": "http://archive.ubuntu.com/ubuntu",
                "os_version": "22.04",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["connectivity_status"] == "connected"
        assert probe.call_args.args[0].pk is None

    def test_edit_form_test_reuses_saved_password_without_mutating_source(
        self, su_client, mocker
    ):
        from apps.core.mixinx import EncryptMixin

        credentials = {"auth_password": "saved-secret"}
        EncryptMixin.encrypt_field("auth_password", credentials)
        source = PatchSource.objects.create(
            name="WSUS-Saved",
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com",
            auth_user="old-user",
            auth_password=credentials["auth_password"],
            team=[1],
        )
        probe = mocker.patch(
            "apps.patch_mgmt.views.patch_source.probe_source",
            return_value=mocker.Mock(reachable=True, status_code=200, detail="ok"),
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/check_connectivity/",
            {"auth_user": "new-user"},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        tested = probe.call_args.args[0]
        assert tested.auth_user == "new-user"
        assert tested.get_auth_password() == "saved-secret"
        source.refresh_from_db()
        assert source.auth_user == "old-user"

    def test_metadata_only_update_keeps_connectivity_and_does_not_probe(
        self, su_client, mocker
    ):
        source = PatchSource.objects.create(
            name="YUM-Old",
            source_type=PatchSourceType.YUM_REPO,
            url="https://repo.example.com",
            connectivity_status="connected",
            team=[1],
        )
        probe = mocker.patch("apps.patch_mgmt.tasks.check_patch_source_connectivity.delay")

        resp = su_client.put(
            f"{PATCH_SOURCE_URL}{source.id}/",
            {
                "name": "YUM-New",
                "source_type": source.source_type,
                "url": source.url,
                "is_enabled": False,
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        source.refresh_from_db()
        assert source.connectivity_status == "connected"
        probe.assert_not_called()

    def test_connection_update_resets_connectivity_and_enqueues_probe(
        self, su_client, mocker
    ):
        source = PatchSource.objects.create(
            name="YUM",
            source_type=PatchSourceType.YUM_REPO,
            url="https://old.example.com",
            connectivity_status="connected",
            team=[1],
        )
        probe = mocker.patch("apps.patch_mgmt.tasks.check_patch_source_connectivity.delay")

        resp = su_client.put(
            f"{PATCH_SOURCE_URL}{source.id}/",
            {
                "name": source.name,
                "source_type": source.source_type,
                "url": "https://new.example.com",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK, resp.data
        source.refresh_from_db()
        assert source.connectivity_status == "unknown"
        probe.assert_called_once_with(source.id)

    def test_create_api_missing_required_name_returns_400(self, su_client):
        """malformed_input: 缺少必填字段 name"""
        data = {"source_type": PatchSourceType.WSUS, "team": [1]}
        resp = su_client.post(PATCH_SOURCE_URL, data, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in str(resp.data)

    def test_create_api_unknown_source_type_returns_400(self, su_client):
        """malformed_input: 无效枚举值"""
        data = {"name": "Bad", "source_type": "invalid_type", "team": [1]}
        resp = su_client.post(PATCH_SOURCE_URL, data, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_catalog_actions_are_removed(self, su_client):
        source = PatchSource.objects.create(
            name="WSUS", source_type=PatchSourceType.WSUS, url="http://wsus.example.com", team=[1]
        )

        search_resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/catalog_search/", {"query": "KB5072653"}, format="json"
        )
        ingest_resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/catalog_ingest/",
            {"entry": {"update_id": "obsolete"}},
            format="json",
        )

        assert search_resp.status_code == status.HTTP_404_NOT_FOUND
        assert ingest_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_set_enabled_returns_200(self, su_client):
        """启停切换 action 不能因 serializer 缺 context 报 500。"""
        src = PatchSource.objects.create(
            name="YUM-Test", source_type=PatchSourceType.YUM_REPO, is_enabled=False, team=[1]
        )
        resp = su_client.post(
            f"{PATCH_SOURCE_URL}{src.id}/set_enabled/", {"is_enabled": True}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["is_enabled"] is True

    def test_set_enabled_requires_bool(self, su_client):
        """is_enabled 缺失返回 400。"""
        src = PatchSource.objects.create(
            name="YUM-Test2", source_type=PatchSourceType.YUM_REPO, team=[1]
        )
        resp = su_client.post(f"{PATCH_SOURCE_URL}{src.id}/set_enabled/", {}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ── Patch Library ViewSet ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPatchViewApi:
    def test_list_api_returns_200(self, su_client):
        resp = su_client.get(PATCH_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_create_api_succeeds_windows(self, su_client):
        data = {
            "title": "2024-01 Security Update KB5034441",
            "os_type": OSType.WINDOWS,
            "severity": "critical",
            "team": [1],
        }
        resp = su_client.post(PATCH_URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["os_type"] == OSType.WINDOWS
        assert resp.data["severity"] == "critical"

    def test_retrieve_api_includes_os_detail_fields(self, su_client):
        p = Patch.objects.create(title="openssl fix", os_type=OSType.LINUX, team=[1])
        resp = su_client.get(f"{PATCH_URL}{p.id}/")
        assert resp.status_code == status.HTTP_200_OK
        # Detail serializer must expose both detail accessors
        assert "linux_detail" in resp.data
        assert "windows_detail" in resp.data

    def test_list_api_filter_by_os_type(self, su_client):
        Patch.objects.create(title="Win-patch", os_type=OSType.WINDOWS, team=[1])
        Patch.objects.create(title="Lin-patch", os_type=OSType.LINUX, team=[1])
        resp = su_client.get(f"{PATCH_URL}?os_type=windows")
        assert resp.status_code == status.HTTP_200_OK

    def test_list_serializer_includes_windows_detail(self, authenticated_user, request_factory):
        """列表序列化器即含 windows_detail（补丁库 Win 列：产品/架构/KB）。"""
        from apps.patch_mgmt.models import WindowsPatchDetail
        from apps.patch_mgmt.serializers.patch import PatchListSerializer

        p = Patch.objects.create(title="KB5034441", os_type=OSType.WINDOWS, team=[1])
        WindowsPatchDetail.objects.create(
            patch=p, kb_number="KB5034441",
            product_list=["Windows Server 2019"], architectures=["x64"],
        )
        request = request_factory.get("/")
        request.user = authenticated_user
        data = PatchListSerializer(p, context={"request": request}).data
        assert data["windows_detail"]["kb_number"] == "KB5034441"
        assert data["windows_detail"]["product_list"] == ["Windows Server 2019"]
        assert data["windows_detail"]["architectures"] == ["x64"]

    def test_list_serializer_includes_linux_detail(self, authenticated_user, request_factory):
        """列表序列化器即含 linux_detail（补丁库 Linux 列：版本/系统版本/repo类型）。"""
        from apps.patch_mgmt.models import LinuxPatchDetail
        from apps.patch_mgmt.serializers.patch import PatchListSerializer

        p = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
        LinuxPatchDetail.objects.create(
            patch=p, pkg_name="openssl", pkg_version="1.1.1k-7",
            distro_name="centos", os_version_range=">=7", repo_type="yum",
        )
        request = request_factory.get("/")
        request.user = authenticated_user
        data = PatchListSerializer(p, context={"request": request}).data
        assert data["linux_detail"]["pkg_version"] == "1.1.1k-7"
        assert data["linux_detail"]["repo_type"] == "yum"
        assert data["linux_detail"]["os_version_range"] == ">=7"


# ── PatchTarget ViewSet ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPatchTargetViewApi:
    def test_list_api_returns_200(self, su_client):
        resp = su_client.get(PATCH_TARGET_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_create_api_succeeds(self, su_client):
        data = {
            "name": "web-srv-01",
            "ip": "192.168.1.10",
            "os_type": OSType.LINUX,
            "team": [1],
        }
        resp = su_client.post(PATCH_TARGET_URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["ip"] == "192.168.1.10"

    def test_retrieve_api_returns_target(self, su_client):
        t = PatchTarget.objects.create(name="db-srv", ip="10.0.0.5", team=[1])
        resp = su_client.get(f"{PATCH_TARGET_URL}{t.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["ip"] == "10.0.0.5"

    def test_retrieve_api_only_exposes_credential_presence(self, su_client):
        target = PatchTarget.objects.create(
            name="credential-srv",
            ip="10.0.0.6",
            team=[1],
            ssh_password="encrypted-ssh-secret",
            winrm_password="encrypted-winrm-secret",
            ssh_key_file="ssh_keys/2026/07/23/id_rsa",
        )

        resp = su_client.get(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_200_OK
        assert "ssh_password" not in resp.data
        assert "winrm_password" not in resp.data
        assert resp.data["has_ssh_password"] is True
        assert resp.data["has_winrm_password"] is True
        assert resp.data["has_ssh_key"] is True
        assert resp.data["ssh_key_file_name"] == "id_rsa"
        assert "ssh_key_file" not in resp.data

    def test_malformed_input_invalid_ip_returns_400(self, su_client):
        """malformed_input: 非法 IP 地址"""
        data = {"name": "bad-host", "ip": "not_an_ip", "os_type": OSType.LINUX, "team": [1]}
        resp = su_client.post(PATCH_TARGET_URL, data, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_api_filter_by_os_type(self, su_client):
        PatchTarget.objects.create(name="win", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        PatchTarget.objects.create(name="lin", ip="10.0.0.2", os_type=OSType.LINUX, team=[1])
        resp = su_client.get(f"{PATCH_TARGET_URL}?os_type=windows")
        assert resp.status_code == status.HTTP_200_OK


# ── Dashboard ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPatchDashboardViewApi:
    def test_stats_api_returns_200(self, su_client):
        resp = su_client.get(DASHBOARD_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_stats_api_returns_expected_top_level_keys(self, su_client):
        resp = su_client.get(DASHBOARD_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert "target_total" in resp.data
        assert "patch_total" in resp.data
        assert "scan_tasks" in resp.data
        assert "install_tasks" in resp.data
        assert "patch_severity_distribution" in resp.data

    def test_stats_api_counts_match_db(self, su_client):
        PatchTarget.objects.create(name="t1", ip="1.1.1.1", team=[1])
        PatchTarget.objects.create(name="t2", ip="1.1.1.2", team=[1])
        Patch.objects.create(title="p1", os_type=OSType.WINDOWS, team=[1])

        resp = su_client.get(DASHBOARD_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK
        # Non-zero counts after creating objects
        assert resp.data["target_total"] >= 2
        assert resp.data["patch_total"] >= 1

    def test_stats_scoped_to_current_team(self, su_client):
        """首页按当前团队收口:超管同样只统计当前团队(current_team=1)。"""
        PatchTarget.objects.create(name="own", ip="1.1.1.1", team=[1])
        PatchTarget.objects.create(name="other-team", ip="2.2.2.2", team=[2])
        Patch.objects.create(title="own-patch", os_type=OSType.WINDOWS, team=[1])
        Patch.objects.create(title="other-patch", os_type=OSType.WINDOWS, team=[2])

        resp = su_client.get(DASHBOARD_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["target_total"] == 1  # 仅团队 1
        assert resp.data["patch_total"] == 1


# ── Risk ViewSet ──────────────────────────────────────────────────────────────

RISK_URL = f"{_BASE}/api/risk/"


@pytest.mark.django_db
class TestRiskViewApi:
    def _setup(self):
        from apps.patch_mgmt.models import PatchBaseline, HostBaselineBinding, BaselineRequirement
        from apps.patch_mgmt.constants import ComplianceStatus

        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        patch = Patch.objects.create(title="Security Update", os_type=OSType.WINDOWS, severity="critical", team=[1])
        baseline = PatchBaseline.objects.create(name="Win2019", os_type=OSType.WINDOWS, team=[1])
        binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
        binding.compliance_status = ComplianceStatus.NON_COMPLIANT
        binding.save(update_fields=["compliance_status", "updated_at"])
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)
        return target, patch, baseline

    def test_risk_list_returns_results(self, su_client):
        self._setup()
        resp = su_client.get(RISK_URL, {"view": "patch"})
        assert resp.status_code == status.HTTP_200_OK
        assert "results" in resp.data
        assert resp.data["count"] >= 1

    def test_risk_list_filters_by_remediation(self, su_client):
        self._setup()
        resp = su_client.get(RISK_URL, {"view": "patch", "remediation": "unplanned"})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["count"] >= 1

    def test_risk_summary_returns_counts(self, su_client):
        self._setup()
        resp = su_client.get(f"{RISK_URL}summary/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total"] >= 1

    def test_risk_remediate_creates_install_task(self, su_client):
        from apps.patch_mgmt.models import GovernanceTask

        target, patch, _baseline = self._setup()
        resp = su_client.post(
            f"{RISK_URL}remediate/",
            {"items": [{"host_id": target.id, "patch_id": patch.id}], "execution_mode": "now"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert GovernanceTask.objects.filter(task_type="install").count() == 1

    def test_risk_reboot_requires_window(self, su_client):
        target, _patch, _baseline = self._setup()
        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {"target_ids": [target.id]},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @staticmethod
    def _valid_reboot_window():
        from datetime import timedelta

        from django.utils import timezone

        start = timezone.now() + timedelta(minutes=10)
        return {
            "execution_mode": "window",
            "execution_window_start": start.isoformat(),
            "execution_window_end": (start + timedelta(hours=1)).isoformat(),
        }

    @staticmethod
    def _mark_pending_reboot(target, patch):
        from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
        from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost

        task = GovernanceTask.objects.create(
            name="安装完成待重启",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.COMPLETED,
            target_list=[target.id],
            patch_list=[patch.id],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="pending_reboot",
            stage_color="warning",
        )

    def test_risk_reboot_rejects_host_not_pending_reboot(self, su_client):
        from apps.patch_mgmt.models import GovernanceTask

        target, _patch, _baseline = self._setup()

        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {"target_ids": [target.id], **self._valid_reboot_window()},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "不是待重启状态" in str(resp.data)
        assert not GovernanceTask.objects.filter(task_type="reboot").exists()

    def test_risk_reboot_accepts_pending_reboot_host(self, su_client):
        from apps.patch_mgmt.models import GovernanceTask

        target, patch, _baseline = self._setup()
        self._mark_pending_reboot(target, patch)

        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {"target_ids": [target.id], **self._valid_reboot_window()},
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert GovernanceTask.objects.filter(task_type="reboot", target_list=[target.id]).exists()

    def test_risk_reboot_rejects_mixed_pending_and_non_pending_hosts(self, su_client):
        from apps.patch_mgmt.models import GovernanceTask

        pending_target, patch, _baseline = self._setup()
        self._mark_pending_reboot(pending_target, patch)
        normal_target = PatchTarget.objects.create(
            name="web-02",
            ip="10.0.0.2",
            os_type=OSType.WINDOWS,
            team=[1],
        )

        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {
                "target_ids": [pending_target.id, normal_target.id],
                **self._valid_reboot_window(),
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "不是待重启状态" in str(resp.data)
        assert not GovernanceTask.objects.filter(task_type="reboot").exists()


# ── Governance Task ViewSet ───────────────────────────────────────────────────

GOVERNANCE_URL = f"{_BASE}/api/governance/"


@pytest.mark.django_db
class TestGovernanceTaskViewApi:
    def test_waiting_host_is_not_counted_as_completed_progress(self, authenticated_user, request_factory):
        from apps.patch_mgmt.constants import GovernanceTaskStatus
        from apps.patch_mgmt.serializers.governance import GovernanceTaskListSerializer

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.PENDING,
            stages=["waiting"],
        )
        request = request_factory.get("/")
        request.user = authenticated_user

        data = GovernanceTaskListSerializer(task, context={"request": request}).data

        assert data["progress"] == "0 / 1"

    def test_reboot_pending_host_is_not_counted_as_completed_progress(self, authenticated_user, request_factory):
        from apps.patch_mgmt.constants import GovernanceTaskStatus
        from apps.patch_mgmt.serializers.governance import GovernanceTaskListSerializer

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.RUNNING,
            stages=["pending_reboot"],
        )
        task.task_type = "reboot"
        task.save(update_fields=["task_type"])
        request = request_factory.get("/")
        request.user = authenticated_user

        data = GovernanceTaskListSerializer(task, context={"request": request}).data

        assert data["progress"] == "0 / 1"

    def test_install_pending_reboot_host_is_counted_as_completed_progress(self, authenticated_user, request_factory):
        from apps.patch_mgmt.constants import GovernanceTaskStatus
        from apps.patch_mgmt.serializers.governance import GovernanceTaskListSerializer

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.COMPLETED,
            stages=["pending_reboot"],
        )
        task.task_type = "install"
        task.save(update_fields=["task_type"])
        request = request_factory.get("/")
        request.user = authenticated_user

        data = GovernanceTaskListSerializer(task, context={"request": request}).data

        assert data["progress"] == "1 / 1"

    def test_create_assess_task_without_name_succeeds(self, su_client):
        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        resp = su_client.post(
            GOVERNANCE_URL,
            {"task_type": "assess", "target_list": [target.id], "execution_mode": "now"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert "id" in resp.data

    @staticmethod
    def _make_cancel_task(*, task_status, stages):
        from apps.patch_mgmt.constants import GovernanceTaskStatus
        from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost

        task = GovernanceTask.objects.create(
            name="cancel-test",
            task_type="install",
            target_list=list(range(1, len(stages) + 1)),
            status=task_status,
            team=[1],
        )
        hosts = [
            GovernanceTaskHost.objects.create(
                task=task,
                target_id=index,
                target_name=f"host-{index}",
                stage=stage,
            )
            for index, stage in enumerate(stages, start=1)
        ]
        return task, hosts

    def test_cancel_pending_task_cancels_all_waiting_hosts_and_records_metadata(self, su_client):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.PENDING,
            stages=["waiting", "waiting"],
        )

        resp = su_client.post(
            f"{GOVERNANCE_URL}{task.id}/cancel/",
            {"reason": "维护窗口调整"},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert task.status == GovernanceTaskStatus.CANCELLED
        assert task.cancel_reason == "维护窗口调整"
        assert task.cancelled_by
        assert task.cancelled_at is not None
        assert set(task.host_results.values_list("stage", flat=True)) == {"cancelled"}

    def test_cancel_running_task_only_cancels_waiting_hosts(self, su_client):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.RUNNING,
            stages=["installing", "waiting", "pending_reboot"],
        )

        resp = su_client.post(
            f"{GOVERNANCE_URL}{task.id}/cancel/",
            {"reason": "停止后续主机"},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert task.status == GovernanceTaskStatus.RUNNING
        assert list(task.host_results.order_by("id").values_list("stage", flat=True)) == [
            "installing",
            "cancelled",
            "pending_reboot",
        ]

    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_cancel_requires_non_blank_reason(self, su_client, reason):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.PENDING,
            stages=["waiting"],
        )
        payload = {} if reason is None else {"reason": reason}

        resp = su_client.post(f"{GOVERNANCE_URL}{task.id}/cancel/", payload, format="json")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        task.refresh_from_db()
        assert task.status == GovernanceTaskStatus.PENDING
        assert task.host_results.get().stage == "waiting"

    def test_cancel_running_task_without_waiting_host_is_rejected(self, su_client):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.RUNNING,
            stages=["installing", "pending_reboot"],
        )

        resp = su_client.post(
            f"{GOVERNANCE_URL}{task.id}/cancel/",
            {"reason": "停止后续主机"},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "没有尚未执行的主机可取消" in resp.data["detail"]

    def test_cancel_terminal_task_is_rejected(self, su_client):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        task, _hosts = self._make_cancel_task(
            task_status=GovernanceTaskStatus.COMPLETED,
            stages=["completed"],
        )

        resp = su_client.post(
            f"{GOVERNANCE_URL}{task.id}/cancel/",
            {"reason": "重复取消"},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["detail"] == "任务已结束，不可取消"

    def test_task_detail_includes_baseline_requirements(self, su_client):
        from apps.patch_mgmt.models import (
            GovernanceTask,
            GovernanceTaskHost,
            HostBaselineBinding,
            HostComplianceSnapshot,
            Patch,
            PatchBaseline,
        )
        from apps.patch_mgmt.models.baseline import BaselineRequirement
        from django.utils import timezone

        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
        baseline = PatchBaseline.objects.create(name="linux-baseline", os_type=OSType.LINUX, team=[1])
        HostBaselineBinding.objects.create(target=target, baseline=baseline)
        patch = Patch.objects.create(title="tar security update", os_type=OSType.LINUX, team=[1])
        req = BaselineRequirement.objects.create(baseline=baseline, patch=patch, condition="tar >= 1.0")
        snapshot = HostComplianceSnapshot.objects.create(
            binding=target.baseline_binding,
            requirement=req,
            satisfied=True,
            evidence={"installed_version": "1.1"},
            reason="tar 已满足版本要求",
            evaluated_at=timezone.now(),
        )
        task = GovernanceTask.objects.create(
            name="install",
            task_type="install",
            target_list=[target.id],
            patch_list=[patch.id],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=task, target_id=target.id, target_name=target.name, target_ip=target.ip
        )

        resp = su_client.get(f"{GOVERNANCE_URL}{task.id}/")
        assert resp.status_code == status.HTTP_200_OK
        host_results = resp.data["host_results"]
        assert len(host_results) == 1
        reqs = host_results[0]["requirements"]
        assert len(reqs) == 1
        assert reqs[0]["baseline_name"] == baseline.name
        assert reqs[0]["patch_title"] == patch.title
        assert reqs[0]["condition"] == req.condition
        assert reqs[0]["satisfied"] is True
        assert reqs[0]["reason"] == snapshot.reason
        assert reqs[0]["evidence"] == snapshot.evidence


# ── Baseline ViewSet ──────────────────────────────────────────────────────────

BASELINE_URL = f"{_BASE}/api/baseline/"


@pytest.mark.django_db
class TestBaselineViewApi:
    def test_bind_hosts_to_baseline(self, su_client):
        from apps.patch_mgmt.models import PatchBaseline, HostBaselineBinding

        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        baseline = PatchBaseline.objects.create(name="Win2019", os_type=OSType.WINDOWS, team=[1])
        resp = su_client.post(f"{BASELINE_URL}{baseline.id}/bind_hosts/", {"target_ids": [target.id]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert HostBaselineBinding.objects.filter(target=target, baseline=baseline).exists()
