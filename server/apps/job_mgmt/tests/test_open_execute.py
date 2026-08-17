"""作业执行 / 状态查询开放接口测试"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import DistributionFile, JobExecution
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser


@pytest.mark.unit
@pytest.mark.django_db
class TestOpenScriptExecuteAndStatus:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create(username="test_api_user", domain="test.com")
        SystemUser.objects.create(username=self.user.username, domain=self.user.domain, group_list=[1])
        self.api_secret_plaintext = UserAPISecret.generate_api_secret()
        UserAPISecret.objects.create(
            username=self.user.username,
            domain=self.user.domain,
            api_secret=self.api_secret_plaintext,
            team=1,
        )

    @pytest.fixture(autouse=True)
    def disable_license(self, settings, monkeypatch):
        settings.LICENSE_MGMT_ENABLED = False
        monkeypatch.setenv("LICENSE_MGMT_ENABLED", "0")

    @pytest.fixture(autouse=True)
    def disable_auth_middleware(self, settings):
        settings.MIDDLEWARE = tuple(
            m for m in settings.MIDDLEWARE if m != "apps.core.middlewares.auth_middleware.AuthMiddleware"
        )

    def _auth(self):
        return {"HTTP_API_AUTHORIZATION": self.api_secret_plaintext}

    def _execute_body(self, **overrides):
        data = {
            "name": "补丁安装",
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "web-01", "ip": "10.0.0.1", "os": "linux"}],
            "script_type": "shell",
            "script_content": "echo hello",
            "team": [99],
        }
        data.update(overrides)
        return data

    def test_script_execute_uses_secret_team(self):
        with patch("apps.job_mgmt.nats_api.execute_script_task.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="celery-1")
            response = self.client.post(
                "/api/v1/job_mgmt/api/open/script_execute",
                self._execute_body(),
                format="json",
                **self._auth(),
            )
        assert response.status_code == 201
        body = response.json()
        assert body["result"] is True
        execution = JobExecution.objects.get(id=body["data"]["task_id"])
        assert execution.team == [1]

    def test_script_execute_rejects_empty_target(self):
        response = self.client.post(
            "/api/v1/job_mgmt/api/open/script_execute",
            self._execute_body(target_list=[]),
            format="json",
            **self._auth(),
        )
        assert response.status_code == 400
        assert response.json()["result"] is False

    def test_job_detail_hides_other_team(self):
        own = JobExecution.objects.create(name="own", job_type=JobType.SCRIPT, status=ExecutionStatus.SUCCESS, team=[1])
        other = JobExecution.objects.create(
            name="other", job_type=JobType.SCRIPT, status=ExecutionStatus.SUCCESS, team=[2]
        )
        own_resp = self.client.get(f"/api/v1/job_mgmt/api/open/job_detail/{own.id}", **self._auth())
        assert own_resp.status_code == 200
        assert own_resp.json()["data"]["task_id"] == own.id

        other_resp = self.client.get(f"/api/v1/job_mgmt/api/open/job_detail/{other.id}", **self._auth())
        assert other_resp.status_code == 404

    def test_job_status_masks_foreign_and_missing(self):
        own = JobExecution.objects.create(
            name="own",
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.RUNNING,
            team=[1],
            total_count=2,
            success_count=1,
        )
        foreign = JobExecution.objects.create(
            name="other",
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.SUCCESS,
            team=[2],
        )
        response = self.client.post(
            "/api/v1/job_mgmt/api/open/job_status",
            {"task_ids": [own.id, foreign.id, 99999]},
            format="json",
            **self._auth(),
        )
        assert response.status_code == 200
        by_id = {item["task_id"]: item for item in response.json()["data"]}
        assert by_id[own.id]["status"] == ExecutionStatus.RUNNING
        assert by_id[foreign.id] == {"task_id": foreign.id, "status": "not_found"}
        assert by_id[99999] == {"task_id": 99999, "status": "not_found"}


@pytest.mark.unit
@pytest.mark.django_db
class TestOpenFileDistribute:
    def setup_method(self):
        self.client = APIClient()
        self.team = Group.objects.create(name="trusted-team")
        self.user = User.objects.create(username="file_app", domain="test.com")
        self.system_user = SystemUser.objects.create(
            username=self.user.username,
            domain=self.user.domain,
            group_list=[self.team.id],
        )
        self.api_secret_plaintext = UserAPISecret.generate_api_secret()
        UserAPISecret.objects.create(
            username=self.user.username,
            domain=self.user.domain,
            api_secret=UserAPISecret.hash_api_secret(self.api_secret_plaintext),
            team=self.team.id,
        )
        self.file = DistributionFile.objects.create(
            original_name="trusted-package.tar.gz",
            file_key="job-files/trusted-package.tar.gz",
            expire_at=timezone.now() + timedelta(days=1),
            team=self.team.id,
        )

    @pytest.fixture(autouse=True)
    def disable_license(self, settings, monkeypatch):
        settings.LICENSE_MGMT_ENABLED = False
        monkeypatch.setenv("LICENSE_MGMT_ENABLED", "0")

    @pytest.fixture(autouse=True)
    def disable_auth_middleware(self, settings):
        settings.MIDDLEWARE = tuple(
            m for m in settings.MIDDLEWARE if m != "apps.core.middlewares.auth_middleware.AuthMiddleware"
        )

    def _auth(self):
        return {"HTTP_API_AUTHORIZATION": self.api_secret_plaintext}

    def _body(self, **overrides):
        data = {
            "name": "可信文件分发",
            "file_keys": [self.file.file_key],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "n1", "name": "web-01", "ip": "10.0.0.1", "os": "linux"}],
            "target_path": "/tmp/patches/",
            "team": [999],
        }
        data.update(overrides)
        return data

    def test_uses_api_secret_team_and_ignores_declared_team(self):
        with patch("apps.job_mgmt.services.dangerous_checker.DangerousChecker.check_path") as mock_check, patch(
            "apps.job_mgmt.nats_api.distribute_files_task.delay"
        ) as mock_delay:
            mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
            mock_delay.return_value.id = "celery-1"
            response = self.client.post(
                "/api/v1/job_mgmt/api/open/distribute_file",
                self._body(),
                format="json",
                **self._auth(),
            )

        assert response.status_code == 201
        execution = JobExecution.objects.get(id=response.json()["data"]["task_id"])
        assert execution.team == [self.team.id]
        mock_check.assert_called_once_with("/tmp/patches/", [self.team.id])

    def test_rejects_file_outside_api_secret_team(self):
        self.file.team = Group.objects.create(name="other-team").id
        self.file.save(update_fields=["team"])

        with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
            response = self.client.post(
                "/api/v1/job_mgmt/api/open/distribute_file",
                self._body(),
                format="json",
                **self._auth(),
            )

        assert response.status_code == 400
        assert not JobExecution.objects.filter(name="可信文件分发").exists()
        mock_delay.assert_not_called()

    @pytest.mark.parametrize("account_state", ["disabled", "inactive"])
    def test_rejects_inactive_principal(self, account_state):
        if account_state == "disabled":
            self.system_user.disabled = True
            self.system_user.save(update_fields=["disabled"])
        else:
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])

        response = self.client.post(
            "/api/v1/job_mgmt/api/open/distribute_file",
            self._body(),
            format="json",
            **self._auth(),
        )

        assert response.status_code == 403
        assert not JobExecution.objects.filter(name="可信文件分发").exists()

    def test_rejects_archived_api_secret_team(self):
        self.team.is_delete = True
        self.team.save(update_fields=["is_delete"])

        response = self.client.post(
            "/api/v1/job_mgmt/api/open/distribute_file",
            self._body(),
            format="json",
            **self._auth(),
        )

        assert response.status_code == 400
        assert not JobExecution.objects.filter(name="可信文件分发").exists()

    @pytest.mark.parametrize("payload", [[], "invalid"])
    def test_rejects_non_object_json_payload(self, payload):
        response = self.client.post(
            "/api/v1/job_mgmt/api/open/distribute_file",
            payload,
            format="json",
            **self._auth(),
        )

        assert response.status_code == 400
        assert not JobExecution.objects.exists()


@pytest.mark.unit
@pytest.mark.django_db
class TestOpenJobList:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create(username="test_api_user", domain="test.com")
        SystemUser.objects.create(username=self.user.username, domain=self.user.domain, group_list=[1])
        self.api_secret_plaintext = UserAPISecret.generate_api_secret()
        UserAPISecret.objects.create(
            username=self.user.username,
            domain=self.user.domain,
            api_secret=self.api_secret_plaintext,
            team=1,
        )

    @pytest.fixture(autouse=True)
    def disable_license(self, settings, monkeypatch):
        settings.LICENSE_MGMT_ENABLED = False
        monkeypatch.setenv("LICENSE_MGMT_ENABLED", "0")

    @pytest.fixture(autouse=True)
    def disable_auth_middleware(self, settings):
        settings.MIDDLEWARE = tuple(
            m for m in settings.MIDDLEWARE if m != "apps.core.middlewares.auth_middleware.AuthMiddleware"
        )

    def _auth(self):
        return {"HTTP_API_AUTHORIZATION": self.api_secret_plaintext}

    def test_job_list_returns_owned_jobs_and_params(self):
        from apps.job_mgmt.models import Playbook, Script

        Script.objects.create(
            name="补丁安装",
            description="安装安全补丁",
            content="echo {{ pkg }}",
            script_type="shell",
            team=[1],
            timeout=120,
            params=[
                {"name": "pkg", "label": "包名", "description": "rpm", "default": "openssl", "is_encrypted": False},
                {"name": "token", "label": "令牌", "description": "", "default": "secret", "is_encrypted": True},
            ],
        )
        Script.objects.create(name="foreign", content="echo", script_type="shell", team=[2])
        Playbook.objects.create(
            name="nginx-deploy",
            description="部署 nginx",
            version="v1.0.0",
            team=[1],
            params=[{"name": "port", "default": "80", "description": "监听端口"}],
        )
        Playbook.objects.create(name="other-pb", team=[2], params=[])

        response = self.client.get("/api/v1/job_mgmt/api/open/job_list", **self._auth())
        assert response.status_code == 200
        data = response.json()["data"]
        script_names = [item["name"] for item in data["scripts"]["items"]]
        playbook_names = [item["name"] for item in data["playbooks"]["items"]]
        assert data["scripts"]["count"] == 1
        assert script_names == ["补丁安装"]
        assert "content" not in data["scripts"]["items"][0]
        params = {p["name"]: p for p in data["scripts"]["items"][0]["params"]}
        assert params["pkg"]["default"] == "openssl"
        assert params["token"]["default"] == "******"
        assert data["playbooks"]["count"] == 1
        assert playbook_names == ["nginx-deploy"]
        assert data["playbooks"]["items"][0]["params"][0]["name"] == "port"

    def test_job_list_rejects_oversize_page(self):
        response = self.client.get("/api/v1/job_mgmt/api/open/job_list?page_size=101", **self._auth())
        assert response.status_code == 400
        assert response.json()["result"] is False
