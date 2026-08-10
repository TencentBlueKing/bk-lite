"""补丁管理 API / View 层集成测试（Todo 9）

测试策略：
  - 所有测试使用 su_client（超管 + current_team=1）穿过鉴权层。
  - 覆盖 HTTP 路由解析、序列化字段、filter、export、自定义 action、错误路径。
  - Celery 任务通过 mocker 隔离 apply_async，防止无 broker 报错。
  - 测试类名包含 View/Api/Export → 全部命中 -k "view or api or export" 过滤器。
"""

import sys

import pytest
from rest_framework import status

from apps.patch_mgmt.constants import (
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
    PatchSourceType,
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
            "auth_user": "svc-wsus",
            "auth_password": "plain-secret",
            "team": [1],
        }
        resp = su_client.post(PATCH_SOURCE_URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "WSUS-Local"
        assert resp.data["source_type"] == PatchSourceType.WSUS

    @pytest.mark.parametrize(
        ("missing_field", "payload"),
        [
            ("auth_user", {"auth_password": "plain-secret"}),
            ("auth_password", {"auth_user": "svc-wsus"}),
        ],
    )
    def test_create_wsus_requires_winrm_credentials(
        self, su_client, missing_field, payload
    ):
        resp = su_client.post(
            PATCH_SOURCE_URL,
            {
                "name": "WSUS-Missing-Credential",
                "source_type": PatchSourceType.WSUS,
                "url": "http://wsus.example.com",
                "team": [1],
                **payload,
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert missing_field in resp.data

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

    def test_unsaved_wsus_connectivity_requires_winrm_credentials(
        self, su_client, mocker
    ):
        probe = mocker.patch(
            "apps.patch_mgmt.views.patch_source.probe_source"
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}test_connectivity/",
            {
                "source_type": PatchSourceType.WSUS,
                "url": "http://wsus.example.com",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "auth_user" in resp.data
        assert "auth_password" in resp.data
        probe.assert_not_called()

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

    def test_edit_form_test_reuses_saved_password_when_request_sends_blank(
        self, su_client, mocker
    ):
        from apps.core.mixinx import EncryptMixin

        credentials = {"auth_password": "saved-secret"}
        EncryptMixin.encrypt_field("auth_password", credentials)
        source = PatchSource.objects.create(
            name="WSUS-Blank-Password",
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com",
            auth_user="saved-user",
            auth_password=credentials["auth_password"],
            team=[1],
        )
        probe = mocker.patch(
            "apps.patch_mgmt.views.patch_source.probe_source",
            return_value=mocker.Mock(reachable=True, status_code=200, detail="ok"),
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/check_connectivity/",
            {
                "name": source.name,
                "source_type": PatchSourceType.WSUS,
                "url": source.url,
                "auth_user": "saved-user",
                "auth_password": "",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        tested = probe.call_args.args[0]
        assert tested.get_auth_password() == "saved-secret"

    def test_edit_form_save_reuses_saved_password_when_request_sends_blank(
        self, su_client, mocker
    ):
        from apps.core.mixinx import EncryptMixin

        credentials = {"auth_password": "saved-secret"}
        EncryptMixin.encrypt_field("auth_password", credentials)
        source = PatchSource.objects.create(
            name="WSUS-Save-Blank-Password",
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com",
            auth_user="saved-user",
            auth_password=credentials["auth_password"],
            team=[1],
        )
        enqueue = mocker.patch(
            "apps.patch_mgmt.tasks.check_patch_source_connectivity.delay"
        )

        resp = su_client.put(
            f"{PATCH_SOURCE_URL}{source.id}/",
            {
                "name": source.name,
                "source_type": PatchSourceType.WSUS,
                "url": source.url,
                "auth_user": "saved-user",
                "auth_password": "",
                "team": [1],
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        source.refresh_from_db()
        assert source.auth_password == credentials["auth_password"]
        assert source.get_auth_password() == "saved-secret"
        enqueue.assert_not_called()

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

    def test_linux_preview_does_not_require_wsus_dependency(
        self, su_client, mocker, monkeypatch
    ):
        source = PatchSource.objects.create(
            name="YUM-Test",
            source_type=PatchSourceType.YUM_REPO,
            url="https://repo.example.com",
            team=[1],
        )
        preview = mocker.patch(
            "apps.patch_mgmt.services.source_sync_service.SourceSyncService.preview_sync_candidates",
            return_value=[],
        )
        monkeypatch.setitem(
            sys.modules,
            "apps.patch_mgmt.services.wsus_sync",
            None,
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/preview_sync/",
            {"search": "", "page": 1, "page_size": 20},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == {"items": [], "total": 0, "page": 1, "page_size": 20}
        preview.assert_called_once_with(source)

    @pytest.mark.integration
    def test_linux_preview_search_matches_any_advisory_package(self, su_client, mocker):
        source = PatchSource.objects.create(
            name="YUM-Test",
            source_type=PatchSourceType.YUM_REPO,
            url="https://repo.example.com",
            team=[1],
        )
        mocker.patch(
            "apps.patch_mgmt.services.source_sync_service.SourceSyncService.preview_sync_candidates",
            return_value=[
                {
                    "key": "RLSA-KERNEL",
                    "name": "kernel",
                    "title": "Important: kernel security update",
                    "version": "1.0-1",
                    "packages": [
                        {"name": "kernel", "version": "1.0-1", "arch": "x86_64"},
                        {"name": "kernel-tools", "version": "1.0-1", "arch": "x86_64"},
                    ],
                },
                {
                    "key": "RLSA-BPFTOOL",
                    "name": "bpftool",
                    "title": "Important: kernel security update",
                    "version": "1.0-1",
                },
            ],
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/preview_sync/",
            {"search": "kernel-tools", "page": 1, "page_size": 20},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total"] == 1
        assert [item["name"] for item in resp.data["items"]] == ["kernel"]

    def test_wsus_preview_missing_dependency_returns_400(
        self, su_client, monkeypatch
    ):
        source = PatchSource.objects.create(
            name="WSUS-Test",
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com",
            team=[1],
        )
        monkeypatch.setitem(
            sys.modules,
            "apps.patch_mgmt.services.wsus_sync",
            None,
        )

        resp = su_client.post(
            f"{PATCH_SOURCE_URL}{source.id}/preview_sync/",
            {"search": "", "page": 1, "page_size": 20},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in resp.data

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

    @pytest.mark.integration
    def test_update_linux_legacy_fields_keeps_package_snapshot_in_sync(self, su_client):
        from apps.patch_mgmt.models import LinuxPatchDetail

        patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
        LinuxPatchDetail.objects.create(
            patch=patch,
            pkg_name="openssl",
            pkg_version="1.0",
            packages=[
                {"name": "openssl", "version": "1.0", "arch": "x86_64"},
                {"name": "openssl-libs", "version": "1.0", "arch": "x86_64"},
            ],
        )

        response = su_client.put(
            f"{PATCH_URL}{patch.id}/",
            {
                "title": "openssl",
                "os_type": OSType.LINUX,
                "team": [1],
                "linux_detail": {
                    "pkg_name": "openssl3",
                    "pkg_version": "3.0",
                    "distro_name": "",
                    "os_version_range": "",
                    "architectures": ["x86_64"],
                    "repo_type": "yum",
                },
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        patch.linux_detail.refresh_from_db()
        assert patch.linux_detail.pkg_name == "openssl3"
        assert patch.linux_detail.pkg_version == "3.0"
        assert patch.linux_detail.packages == [
            {"name": "openssl3", "version": "3.0", "arch": "x86_64"},
            {"name": "openssl-libs", "version": "1.0", "arch": "x86_64"},
        ]


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

    def test_retrieve_api_ignores_completed_pending_reboot_history(self, su_client):
        target = PatchTarget.objects.create(name="history-host", ip="10.0.0.29", team=[1])
        task = GovernanceTask.objects.create(
            name="completed-install-history",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.COMPLETED,
            target_list=[target.id],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="pending_reboot",
        )

        resp = su_client.get(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["has_pending_reboot"] is False

    def test_retrieve_api_marks_current_pending_reboot_binding(self, su_client):
        target = PatchTarget.objects.create(name="current-reboot-host", ip="10.0.0.30", team=[1])
        baseline = PatchBaseline.objects.create(name="current-reboot-baseline", os_type=OSType.LINUX, team=[1])
        HostBaselineBinding.objects.create(
            target=target,
            baseline=baseline,
            pending_reboot_count=1,
        )

        resp = su_client.get(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["has_pending_reboot"] is True

    def test_malformed_input_invalid_ip_returns_400(self, su_client):
        """malformed_input: 非法 IP 地址"""
        data = {"name": "bad-host", "ip": "not_an_ip", "os_type": OSType.LINUX, "team": [1]}
        resp = su_client.post(PATCH_TARGET_URL, data, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy_api_rejects_target_with_active_task(self, su_client):
        target = PatchTarget.objects.create(name="busy-host", ip="10.0.0.31", team=[1])
        task = GovernanceTask.objects.create(
            name="active-install",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.RUNNING,
            target_list=[target.id],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="installing",
        )

        resp = su_client.delete(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.data["code"] == "target_has_active_task"
        assert resp.data["message"]
        assert PatchTarget.objects.filter(pk=target.id).exists()

    def test_destroy_api_rejects_target_with_pending_reboot_binding(self, su_client):
        target = PatchTarget.objects.create(name="pending-host", ip="10.0.0.32", team=[1])
        baseline = PatchBaseline.objects.create(name="pending-baseline", os_type=OSType.LINUX, team=[1])
        HostBaselineBinding.objects.create(
            target=target,
            baseline=baseline,
            pending_reboot_count=1,
        )

        resp = su_client.delete(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.data["code"] == "target_pending_reboot"
        assert resp.data["message"]
        assert PatchTarget.objects.filter(pk=target.id).exists()

    def test_destroy_api_allows_completed_pending_reboot_history(self, su_client):
        target = PatchTarget.objects.create(name="reboot-host", ip="10.0.0.33", team=[1])
        task = GovernanceTask.objects.create(
            name="completed-install",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.COMPLETED,
            target_list=[target.id],
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="pending_reboot",
        )

        resp = su_client.delete(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_200_OK
        assert not PatchTarget.objects.filter(pk=target.id).exists()
        assert not GovernanceTaskHost.objects.filter(task_id=task.id, target_id=target.id).exists()
        assert not GovernanceTask.objects.filter(pk=task.id).exists()

    def test_destroy_api_removes_binding_key_and_patch_history(self, su_client, mocker):
        target = PatchTarget.objects.create(
            name="retired-host",
            ip="10.0.0.34",
            team=[1],
            ssh_key_file="ssh_keys/2026/08/03/id_rsa",
        )
        baseline = PatchBaseline.objects.create(name="retired-baseline", os_type=OSType.LINUX, team=[1])
        HostBaselineBinding.objects.create(target=target, baseline=baseline)
        task = GovernanceTask.objects.create(
            name="completed-assessment",
            task_type=GovernanceTaskType.ASSESS,
            status=GovernanceTaskStatus.COMPLETED,
            target_list=[target.id],
            team=[1],
        )
        history = GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="completed",
        )
        storage_delete = mocker.patch.object(
            PatchTarget._meta.get_field("ssh_key_file").storage,
            "delete",
        )

        resp = su_client.delete(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_200_OK
        assert not PatchTarget.objects.filter(pk=target.id).exists()
        assert not HostBaselineBinding.objects.filter(target_id=target.id).exists()
        assert not GovernanceTaskHost.objects.filter(pk=history.id).exists()
        assert not GovernanceTask.objects.filter(pk=task.id).exists()
        storage_delete.assert_called_once_with("ssh_keys/2026/08/03/id_rsa")

    def test_destroy_api_keeps_target_when_key_cleanup_fails(self, su_client, mocker):
        target = PatchTarget.objects.create(
            name="key-cleanup-host",
            ip="10.0.0.35",
            team=[1],
            ssh_key_file="ssh_keys/2026/08/03/id_rsa",
        )
        mocker.patch.object(
            PatchTarget._meta.get_field("ssh_key_file").storage,
            "delete",
            side_effect=OSError("storage unavailable"),
        )

        resp = su_client.delete(f"{PATCH_TARGET_URL}{target.id}/")

        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert resp.data["code"] == "target_key_cleanup_failed"
        assert resp.data["message"]
        assert PatchTarget.objects.filter(pk=target.id).exists()

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
        target = PatchTarget.objects.create(name="t1", ip="1.1.1.1", team=[1])
        PatchTarget.objects.create(name="t2", ip="1.1.1.2", team=[1])
        patch = Patch.objects.create(title="p1", os_type=OSType.WINDOWS, team=[1])
        baseline = PatchBaseline.objects.create(name="b1", os_type=OSType.WINDOWS, team=[1])
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)
        HostBaselineBinding.objects.create(target=target, baseline=baseline)

        resp = su_client.get(DASHBOARD_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK
        # Non-zero counts after creating objects
        assert resp.data["target_total"] >= 2
        assert resp.data["patch_total"] >= 1

    def test_superuser_dashboard_includes_all_target_roots(self, su_client):
        own = PatchTarget.objects.create(name="own", ip="1.1.1.1", team=[1])
        other = PatchTarget.objects.create(name="other-team", ip="2.2.2.2", team=[2])
        own_patch = Patch.objects.create(title="own-patch", os_type=OSType.WINDOWS, team=[1])
        other_patch = Patch.objects.create(title="other-patch", os_type=OSType.WINDOWS, team=[2])
        own_baseline = PatchBaseline.objects.create(name="own-b", os_type=OSType.WINDOWS, team=[1])
        other_baseline = PatchBaseline.objects.create(name="other-b", os_type=OSType.WINDOWS, team=[2])
        BaselineRequirement.objects.create(baseline=own_baseline, patch=own_patch)
        BaselineRequirement.objects.create(baseline=other_baseline, patch=other_patch)
        HostBaselineBinding.objects.create(target=own, baseline=own_baseline)
        HostBaselineBinding.objects.create(target=other, baseline=other_baseline)

        resp = su_client.get(DASHBOARD_STATS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["target_total"] == 2
        assert resp.data["patch_total"] == 2

    def test_recent_tasks_mirror_visible_execution_record_roots(self, su_client):
        target = PatchTarget.objects.create(name="record-host", ip="10.0.0.88", team=[1])
        install = GovernanceTask.objects.create(
            name="治理记录",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.COMPLETED,
            execution_mode="now",
            team=[1],
        )
        GovernanceTask.objects.create(
            name="内部验证",
            task_type=GovernanceTaskType.VERIFY,
            status=GovernanceTaskStatus.COMPLETED,
            parent_task=install,
            team=[1],
        )
        GovernanceTask.objects.create(
            name="评估",
            task_type=GovernanceTaskType.ASSESS,
            status=GovernanceTaskStatus.COMPLETED,
            team=[1],
        )
        reboot = GovernanceTask.objects.create(
            name="重启记录",
            task_type=GovernanceTaskType.REBOOT,
            status=GovernanceTaskStatus.PENDING,
            execution_mode="window",
            team=[1],
        )
        GovernanceTaskHost.objects.create(task=install, target_id=target.id, target_name=target.name, stage="completed")
        GovernanceTaskHost.objects.create(task=reboot, target_id=target.id, target_name=target.name, stage="waiting")

        resp = su_client.get(DASHBOARD_STATS_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert [item["id"] for item in resp.data["recent_tasks"]] == [reboot.id, install.id]
        assert set(resp.data["recent_tasks"][0]) == {
            "id",
            "name",
            "task_type",
            "task_type_display",
            "execution_mode",
            "execution_window_start",
            "execution_window_end",
            "status",
            "status_code",
            "status_color",
            "created_at",
        }


# ── Risk ViewSet ──────────────────────────────────────────────────────────────

RISK_URL = f"{_BASE}/api/risk/"


@pytest.mark.django_db
class TestRiskViewApi:
    def _setup(self):
        from django.utils import timezone

        from apps.patch_mgmt.constants import ComplianceStatus, RequirementAssessmentStatus
        from apps.patch_mgmt.models import (
            BaselineRequirement,
            HostBaselineBinding,
            HostComplianceSnapshot,
            PatchBaseline,
            WindowsPatchDetail,
        )

        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        patch = Patch.objects.create(title="Security Update", os_type=OSType.WINDOWS, severity="critical", team=[1])
        WindowsPatchDetail.objects.create(patch=patch, kb_number="KB5000003")
        baseline = PatchBaseline.objects.create(name="Win2019", os_type=OSType.WINDOWS, team=[1])
        binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
        binding.compliance_status = ComplianceStatus.NON_COMPLIANT
        binding.save(update_fields=["compliance_status", "updated_at"])
        requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
        HostComplianceSnapshot.objects.create(
            binding=binding,
            requirement=requirement,
            satisfied=False,
            status=RequirementAssessmentStatus.MISSING,
            reason="KB5000003 适用但未安装",
            evaluated_at=timezone.now(),
        )
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

    def test_risk_remediate_creates_install_task(self, su_client, mocker):
        from apps.patch_mgmt.models import GovernanceTask

        trigger = mocker.patch(
            "apps.patch_mgmt.services.governance_service._trigger_async"
        )
        target, patch, _baseline = self._setup()
        resp = su_client.post(
            f"{RISK_URL}remediate/",
            {"name": "治理任务", "items": [{"host_id": target.id, "patch_id": patch.id}], "execution_mode": "now"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        task = GovernanceTask.objects.get(task_type="install")
        trigger.assert_called_once_with(task.id)

    def test_risk_remediate_preserves_preview_failure_warning(self, su_client, mocker):
        from apps.patch_mgmt.models import GovernanceTask, HostComplianceSnapshot

        mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")
        target, patch, _baseline = self._setup()
        HostComplianceSnapshot.objects.filter(
            binding__target=target,
            requirement__patch=patch,
        ).update(
            evidence={
                "install_impact": {
                    "summary": "",
                    "error": "apt-get dry-run failed",
                }
            }
        )

        response = su_client.post(
            f"{RISK_URL}remediate/",
            {
                "name": "坚持治理任务",
                "items": [{"host_id": target.id, "patch_id": patch.id}],
                "execution_mode": "now",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        risk_snapshot = GovernanceTask.objects.get(task_type="install").risk_snapshot
        assert risk_snapshot[0]["preview_warning"] == "apt-get dry-run failed"

    def test_risk_remediate_requires_task_name(self, su_client):
        target, patch, _baseline = self._setup()

        response = su_client.post(
            f"{RISK_URL}remediate/",
            {
                "items": [{"host_id": target.id, "patch_id": patch.id}],
                "execution_mode": "now",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "task_name_required"

    def test_risk_remediate_rejects_requirement_that_is_not_missing(self, su_client, mocker):
        from apps.patch_mgmt.constants import RequirementAssessmentStatus
        from apps.patch_mgmt.models import HostComplianceSnapshot

        trigger = mocker.patch(
            "apps.patch_mgmt.services.governance_service._trigger_async"
        )
        target, patch, _baseline = self._setup()
        HostComplianceSnapshot.objects.filter(
            binding__target=target,
            requirement__patch=patch,
        ).update(
            status=RequirementAssessmentStatus.NOT_APPLICABLE,
            satisfied=False,
            reason="不适用于当前主机",
        )

        resp = su_client.post(
            f"{RISK_URL}remediate/",
            {"name": "治理任务", "items": [{"host_id": target.id, "patch_id": patch.id}], "execution_mode": "now"},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "patches_not_remediable"
        trigger.assert_not_called()

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
        return task

    def test_risk_reboot_rejects_host_not_pending_reboot(self, su_client):
        from apps.patch_mgmt.models import GovernanceTask

        target, _patch, _baseline = self._setup()

        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {"name": "重启任务", "target_ids": [target.id], **self._valid_reboot_window()},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "targets_not_pending_reboot"
        assert str(target.id) in resp.data["detail"]
        assert not GovernanceTask.objects.filter(task_type="reboot").exists()

    def test_risk_reboot_accepts_pending_reboot_host(self, su_client, mocker):
        from apps.patch_mgmt.models import GovernanceTask

        trigger = mocker.patch(
            "apps.patch_mgmt.services.governance_service._trigger_async"
        )
        target, patch, _baseline = self._setup()
        self._mark_pending_reboot(target, patch)

        preview = su_client.post(
            f"{RISK_URL}reboot_preview/",
            {"target_ids": [target.id]},
            format="json",
        )
        assert preview.status_code == status.HTTP_200_OK
        assert preview.data["target_ids"] == [target.id]
        assert [(item["host_id"], item["patch_id"]) for item in preview.data["items"]] == [
            (target.id, patch.id)
        ]

        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {
                "target_ids": [target.id],
                "name": "重启任务",
                "scope_token": preview.data["scope_token"],
                **self._valid_reboot_window(),
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        task = GovernanceTask.objects.get(task_type="reboot", target_list=[target.id])
        trigger.assert_called_once_with(task.id)

    def test_risk_reboot_rejects_stale_scope_token(self, su_client):
        target, patch, _baseline = self._setup()
        self._mark_pending_reboot(target, patch)

        resp = su_client.post(
            f"{RISK_URL}reboot/",
            {
                "target_ids": [target.id],
                "name": "重启任务",
                "scope_token": "stale-token",
                **self._valid_reboot_window(),
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "reboot_scope_changed"

    def test_reboot_preview_source_record_ignores_later_failed_install(self, su_client):
        from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
        from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost

        target, patch, baseline = self._setup()
        completed = self._mark_pending_reboot(target, patch)
        risk_snapshot = [
            {
                "id": f"{target.id}:{patch.id}:{baseline.id}",
                "host_id": target.id,
                "patch_id": patch.id,
                "baseline_id": baseline.id,
            }
        ]
        completed.risk_snapshot = risk_snapshot
        completed.save(update_fields=["risk_snapshot", "updated_at"])
        failed = GovernanceTask.objects.create(
            name="later failed install",
            task_type=GovernanceTaskType.INSTALL,
            status=GovernanceTaskStatus.FAILED,
            target_list=[target.id],
            patch_list=[patch.id],
            risk_snapshot=risk_snapshot,
            team=[1],
        )
        GovernanceTaskHost.objects.create(
            task=failed,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="failed",
            stage_color="error",
        )

        preview = su_client.post(
            f"{RISK_URL}reboot_preview/",
            {"target_ids": [target.id]},
            format="json",
        )

        assert preview.status_code == status.HTTP_200_OK
        assert preview.data["items"][0]["source_record_id"] == completed.id

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
                "name": "重启任务",
                "target_ids": [pending_target.id, normal_target.id],
                **self._valid_reboot_window(),
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "targets_not_pending_reboot"
        assert str(normal_target.id) in resp.data["detail"]
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

    def test_create_assess_task_without_name_succeeds(self, su_client, mocker):
        trigger = mocker.patch(
            "apps.patch_mgmt.services.governance_service._trigger_async"
        )
        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        resp = su_client.post(
            GOVERNANCE_URL,
            {"task_type": "assess", "target_list": [target.id], "execution_mode": "now"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert "id" in resp.data
        trigger.assert_called_once_with(resp.data["id"])

    def test_manual_verify_task_is_rejected(self, su_client):
        target = PatchTarget.objects.create(
            name="web-verify", ip="10.0.0.9", os_type=OSType.WINDOWS, team=[1]
        )

        resp = su_client.post(
            GOVERNANCE_URL,
            {"task_type": "verify", "target_list": [target.id], "execution_mode": "now"},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "manual_verify_not_supported"

    @staticmethod
    def _make_cancel_task(*, task_status, stages):
        from apps.patch_mgmt.constants import GovernanceTaskStatus
        from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost

        targets = [
            PatchTarget.objects.create(
                name=f"host-{index}", ip=f"10.20.0.{index}", team=[1]
            )
            for index in range(1, len(stages) + 1)
        ]
        task = GovernanceTask.objects.create(
            name="cancel-test",
            task_type="install",
            target_list=[target.id for target in targets],
            status=task_status,
            team=[1],
        )
        hosts = [
            GovernanceTaskHost.objects.create(
                task=task,
                target_id=target.id,
                target_name=f"host-{index}",
                stage=stage,
            )
            for index, (target, stage) in enumerate(zip(targets, stages), start=1)
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
        assert resp.data["code"] == "no_waiting_hosts_to_cancel"
        assert resp.data["detail"]

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
        assert resp.data["code"] == "task_finished_not_cancellable"
        assert resp.data["detail"]

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
    def test_requirements_api_returns_windows_version_and_arch(self, su_client):
        from apps.patch_mgmt.models import (
            BaselineRequirement,
            PatchBaseline,
            WindowsPatchDetail,
        )

        baseline = PatchBaseline.objects.create(
            name="Windows Server 基线",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        patch = Patch.objects.create(
            title="KB6000010",
            os_type=OSType.WINDOWS,
            team=[1],
        )
        WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB6000010",
            product_list=["Windows Server 2019", "Windows Server 2022"],
            architectures=["x64", "arm64"],
        )
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)

        resp = su_client.get(f"{BASELINE_URL}{baseline.id}/requirements/")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data[0]["patch_version"] == "Windows Server 2019, Windows Server 2022"
        assert resp.data[0]["patch_arch"] == "x64, arm64"

    def test_bind_hosts_to_baseline(self, su_client):
        from apps.patch_mgmt.models import PatchBaseline, HostBaselineBinding

        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])
        baseline = PatchBaseline.objects.create(name="Win2019", os_type=OSType.WINDOWS, team=[1])
        resp = su_client.post(f"{BASELINE_URL}{baseline.id}/bind_hosts/", {"target_ids": [target.id]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert HostBaselineBinding.objects.filter(target=target, baseline=baseline).exists()

    def test_hosts_api_returns_bound_targets_with_permissions(self, su_client):
        from apps.patch_mgmt.models import HostBaselineBinding, PatchBaseline

        target = PatchTarget.objects.create(
            name="bound-web-01",
            ip="10.0.0.2",
            os_type=OSType.LINUX,
            team=[1],
        )
        baseline = PatchBaseline.objects.create(
            name="Linux baseline",
            os_type=OSType.LINUX,
            team=[1],
        )
        HostBaselineBinding.objects.create(target=target, baseline=baseline)

        resp = su_client.get(f"{BASELINE_URL}{baseline.id}/hosts/")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == [
            {
                "id": resp.data[0]["id"],
                "target": target.id,
                "target_name": target.name,
                "target_ip": target.ip,
                "baseline": baseline.id,
                "baseline_name": baseline.name,
                "permission": ["View", "Operate"],
                "created_by": "",
                "created_at": resp.data[0]["created_at"],
            }
        ]
