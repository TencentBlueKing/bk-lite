"""文件上传开放接口单元测试"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret


@pytest.mark.unit
@pytest.mark.django_db
class TestOpenFileUploadView:
    """
    文件上传接口测试

    鉴权由全局 APISecretMiddleware 处理：
    - Header: Api-Authorization: <api_secret>
    - 中间件验证后设置 request.user 和 request.api_pass=True
    """

    def setup_method(self):
        self.client = APIClient()
        self.url = "/api/v1/job_mgmt/api/open/upload_file"
        # 创建测试用户和 API Secret
        self.user = User.objects.create(username="test_api_user", domain="test.com")
        self.api_secret = UserAPISecret.objects.create(
            username=self.user.username,
            domain=self.user.domain,
            api_secret=UserAPISecret.generate_api_secret(),
            team=1,
        )

    @pytest.fixture(autouse=True)
    def disable_license(self, settings, monkeypatch):
        settings.LICENSE_MGMT_ENABLED = False
        monkeypatch.setenv("LICENSE_MGMT_ENABLED", "0")

    @pytest.fixture(autouse=True)
    def disable_auth_middleware(self, settings):
        """Re-enable APISecretMiddleware (overrides global conftest fixture)."""
        # Keep APISecretMiddleware active for these tests since we test middleware-based auth.
        # Only remove AuthMiddleware so it doesn't try to verify tokens via system_mgmt RPC.
        settings.MIDDLEWARE = tuple(m for m in settings.MIDDLEWARE if m != "apps.core.middlewares.auth_middleware.AuthMiddleware")

    def test_no_auth_header_returns_401(self):
        """无 Api-Authorization header 时被 AuthMiddleware 拦截"""
        file = SimpleUploadedFile("test.txt", b"content")
        response = self.client.post(self.url, {"file": file}, format="multipart")
        # AuthMiddleware 返回 401
        assert response.status_code in (401, 403)

    def test_invalid_token_returns_403(self):
        """无效 token 被 APISecretMiddleware 拦截返回 403"""
        file = SimpleUploadedFile("test.txt", b"content")
        response = self.client.post(
            self.url,
            {"file": file},
            format="multipart",
            HTTP_API_AUTHORIZATION="invalid_token_xxx",
        )
        assert response.status_code == 403

    def test_no_file_returns_400(self):
        """合法 token 但未上传文件返回 400"""
        response = self.client.post(
            self.url,
            {},
            format="multipart",
            HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
        )
        assert response.status_code == 400
        data = response.json()
        assert data["result"] is False
        assert "未上传文件" in data["message"]

    def test_success_upload(self):
        """合法 token + 文件上传成功"""
        file = SimpleUploadedFile("patch-1.0.rpm", b"binary content")

        with patch("apps.job_mgmt.views.open_api.async_to_sync") as mock_async:
            mock_async.return_value = MagicMock()
            response = self.client.post(
                self.url,
                {"file": file},
                format="multipart",
                HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["result"] is True
        assert "file_id" in data["data"]
        assert "file_key" in data["data"]
        assert data["data"]["file_key"].endswith(".rpm")

    def test_upload_permanent_file(self):
        """上传永久保存文件（permanent=true）"""
        from apps.job_mgmt.models import DistributionFile

        file = SimpleUploadedFile("permanent-patch.rpm", b"binary content")

        with patch("apps.job_mgmt.views.open_api.async_to_sync") as mock_async:
            mock_async.return_value = MagicMock()
            response = self.client.post(
                self.url,
                {"file": file, "permanent": "true"},
                format="multipart",
                HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
            )

        assert response.status_code == 201
        data = response.json()
        file_id = data["data"]["file_id"]

        # 验证数据库记录的 is_permanent 字段和 team 字段
        df = DistributionFile.objects.get(id=file_id)
        assert df.is_permanent is True
        assert df.team == self.api_secret.team

    def test_upload_temporary_file_default(self):
        """上传临时文件（不传 permanent 参数，默认 false）"""
        from apps.job_mgmt.models import DistributionFile

        file = SimpleUploadedFile("temp-patch.rpm", b"binary content")

        with patch("apps.job_mgmt.views.open_api.async_to_sync") as mock_async:
            mock_async.return_value = MagicMock()
            response = self.client.post(
                self.url,
                {"file": file},
                format="multipart",
                HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
            )

        assert response.status_code == 201
        data = response.json()
        file_id = data["data"]["file_id"]

        # 验证数据库记录的 is_permanent 字段为 False
        df = DistributionFile.objects.get(id=file_id)
        assert df.is_permanent is False

    def test_upload_temporary_file_explicit(self):
        """显式上传临时文件（permanent=false）"""
        from apps.job_mgmt.models import DistributionFile

        file = SimpleUploadedFile("explicit-temp.rpm", b"binary content")

        with patch("apps.job_mgmt.views.open_api.async_to_sync") as mock_async:
            mock_async.return_value = MagicMock()
            response = self.client.post(
                self.url,
                {"file": file, "permanent": "false"},
                format="multipart",
                HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
            )

        assert response.status_code == 201
        data = response.json()
        file_id = data["data"]["file_id"]

        df = DistributionFile.objects.get(id=file_id)
        assert df.is_permanent is False


@pytest.mark.unit
@pytest.mark.django_db
class TestOpenFileDeleteView:
    """文件删除接口测试"""

    def setup_method(self):
        self.client = APIClient()
        self.url = "/api/v1/job_mgmt/api/open/delete_file"
        self.user = User.objects.create(username="test_api_user", domain="test.com")
        self.api_secret = UserAPISecret.objects.create(
            username=self.user.username,
            domain=self.user.domain,
            api_secret=UserAPISecret.generate_api_secret(),
            team=1,
        )

    @pytest.fixture(autouse=True)
    def disable_license(self, settings, monkeypatch):
        settings.LICENSE_MGMT_ENABLED = False
        monkeypatch.setenv("LICENSE_MGMT_ENABLED", "0")

    @pytest.fixture(autouse=True)
    def disable_auth_middleware(self, settings):
        """Re-enable APISecretMiddleware for these tests."""
        settings.MIDDLEWARE = tuple(m for m in settings.MIDDLEWARE if m != "apps.core.middlewares.auth_middleware.AuthMiddleware")

    def test_no_auth_returns_403(self):
        response = self.client.delete(
            self.url,
            {"files": [{"file_id": 1, "file_key": "job-files/2026/01/01/test.rpm"}]},
            format="json",
        )
        assert response.status_code == 403

    def test_empty_files_returns_400(self):
        response = self.client.delete(
            self.url,
            {"files": []},
            format="json",
            HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
        )
        assert response.status_code == 400

    def test_mismatched_id_and_key(self):
        """file_id 和 file_key 不匹配时返回 not_found"""
        from apps.job_mgmt.models import DistributionFile

        df = DistributionFile.objects.create(
            original_name="patch.rpm",
            file_key="job-files/2026/05/06/abc123.rpm",
            team=self.api_secret.team,
        )

        response = self.client.delete(
            self.url,
            {"files": [{"file_id": df.id, "file_key": "job-files/wrong/key.rpm"}]},
            format="json",
            HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted"] == 0
        assert "not_found" in data
        assert DistributionFile.objects.filter(id=df.id).exists()

    def test_delete_existing_file(self):
        """同组用户删除文件成功"""
        from apps.job_mgmt.models import DistributionFile

        df = DistributionFile.objects.create(
            original_name="patch.rpm",
            file_key="job-files/2026/05/06/abc123.rpm",
            team=self.api_secret.team,  # 同组
        )

        with patch("apps.job_mgmt.views.open_api.async_to_sync") as mock_async:
            mock_async.return_value = MagicMock()
            response = self.client.delete(
                self.url,
                {"files": [{"file_id": df.id, "file_key": df.file_key}]},
                format="json",
                HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
            )

        assert response.status_code == 200
        assert response.json()["data"]["deleted"] == 1
        assert not DistributionFile.objects.filter(id=df.id).exists()

    def test_delete_cross_team_file_fails(self):
        """跨组删除文件失败（返回 no_permission）"""
        from apps.job_mgmt.models import DistributionFile

        df = DistributionFile.objects.create(
            original_name="other-team-patch.rpm",
            file_key="job-files/2026/05/06/other123.rpm",
            team=999,  # 不同组
        )

        response = self.client.delete(
            self.url,
            {"files": [{"file_id": df.id, "file_key": df.file_key}]},
            format="json",
            HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted"] == 0
        assert "no_permission" in data
        assert len(data["no_permission"]) == 1
        assert data["no_permission"][0]["file_id"] == df.id
        # 文件仍然存在
        assert DistributionFile.objects.filter(id=df.id).exists()

    def test_delete_legacy_file_without_team_fails(self):
        """历史文件（无 team）无法通过 open API 删除"""
        from apps.job_mgmt.models import DistributionFile

        df = DistributionFile.objects.create(
            original_name="legacy-patch.rpm",
            file_key="job-files/2026/05/06/legacy123.rpm",
            team=None,  # 历史数据无 team
        )

        response = self.client.delete(
            self.url,
            {"files": [{"file_id": df.id, "file_key": df.file_key}]},
            format="json",
            HTTP_API_AUTHORIZATION=self.api_secret.api_secret,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted"] == 0
        assert "no_permission" in data
        # 文件仍然存在
        assert DistributionFile.objects.filter(id=df.id).exists()
