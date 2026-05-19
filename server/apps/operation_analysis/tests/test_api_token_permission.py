"""
API Token 权限校验集成测试

测试 operation_analysis 模块的 API Token 权限校验：
- API Token 用户有权限时可以正常访问
- API Token 用户无权限时返回 403
"""

from types import SimpleNamespace
from unittest.mock import patch

from rest_framework import status

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils


class MockUser:
    """模拟用户对象"""

    def __init__(
        self,
        username="testuser",
        domain="domain.com",
        group_list=None,
        roles=None,
        permission=None,
        is_superuser=False,
    ):
        self.id = 1
        self.username = username
        self.domain = domain
        self.group_list = group_list or [1]
        self.roles = roles or []
        self.permission = permission or {}
        self.is_superuser = is_superuser
        self.role_ids = []
        self.locale = "en"
        self.is_authenticated = True


def _make_request(user, api_pass=False):
    """构建模拟请求"""
    request = SimpleNamespace()
    request.user = user
    request.api_pass = api_pass
    request.COOKIES = {"current_team": "1"}
    return request


class TestApiTokenPermissionIntegration:
    """API Token 权限校验集成测试 - 测试 HasPermission 装饰器在 operation_analysis 场景下的行为"""

    def test_api_token_with_view_permission_can_list(self):
        """测试 API Token 用户有 view-View 权限时可以访问列表"""

        @HasPermission("view-View", app_name="ops-analysis")
        def list_view(request):
            return SimpleNamespace(status_code=200)

        user = MockUser(
            username="viewer",
            roles=["ops-analysis--viewer"],
            permission={"ops-analysis": {"view-View"}},
            is_superuser=False,
        )

        request = _make_request(user, api_pass=True)
        response = list_view(request)

        # 有权限应该能访问（不是 403）
        assert response.status_code == 200

    def test_api_token_without_permission_denied(self):
        """测试 API Token 用户无权限时返回 403"""

        @HasPermission("view-View", app_name="ops-analysis")
        def list_view(request):
            return SimpleNamespace(status_code=200)

        user = MockUser(
            username="noperm",
            roles=[],
            permission={},  # 没有任何权限
            is_superuser=False,
        )

        request = _make_request(user, api_pass=True)

        with patch.object(WebUtils, "response_403") as mock_403:
            mock_403.return_value = SimpleNamespace(status_code=403)
            response = list_view(request)

        # 无权限应该返回 403
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_api_token_superuser_can_access(self):
        """测试 API Token 超级用户可以访问"""

        @HasPermission("view-View", app_name="ops-analysis")
        def list_view(request):
            return SimpleNamespace(status_code=200)

        user = MockUser(
            username="superadmin",
            roles=["admin"],
            permission={},  # 超级用户不需要具体权限
            is_superuser=True,
        )

        request = _make_request(user, api_pass=True)
        response = list_view(request)

        # 超级用户应该能访问
        assert response.status_code == 200

    def test_api_token_create_without_permission_denied(self):
        """测试 API Token 用户无创建权限时返回 403"""

        @HasPermission("view-AddView", app_name="ops-analysis")
        def create_view(request):
            return SimpleNamespace(status_code=201)

        user = MockUser(
            username="viewer_only",
            roles=["ops-analysis--viewer"],
            permission={"ops-analysis": {"view-View"}},  # 只有查看权限，没有创建权限
            is_superuser=False,
        )

        request = _make_request(user, api_pass=True)

        with patch.object(WebUtils, "response_403") as mock_403:
            mock_403.return_value = SimpleNamespace(status_code=403)
            response = create_view(request)

        # 无创建权限应该返回 403
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_api_token_with_create_permission_can_create(self):
        """测试 API Token 用户有创建权限时可以创建"""

        @HasPermission("view-AddView", app_name="ops-analysis")
        def create_view(request):
            return SimpleNamespace(status_code=201)

        user = MockUser(
            username="editor",
            roles=["ops-analysis--editor"],
            permission={"ops-analysis": {"view-View", "view-AddView"}},
            is_superuser=False,
        )

        request = _make_request(user, api_pass=True)
        response = create_view(request)

        # 有创建权限应该能创建
        assert response.status_code == 201

    def test_web_token_still_works(self):
        """测试 Web Token 用户（非 api_pass）仍然正常工作"""

        @HasPermission("view-View", app_name="ops-analysis")
        def list_view(request):
            return SimpleNamespace(status_code=200)

        user = MockUser(
            username="webuser",
            roles=["ops-analysis--viewer"],
            permission={"ops-analysis": {"view-View"}},
            is_superuser=False,
        )

        request = _make_request(user, api_pass=False)  # Web Token
        response = list_view(request)

        # Web Token 用户有权限应该能访问
        assert response.status_code == 200

    def test_web_token_without_permission_denied(self):
        """测试 Web Token 用户无权限时返回 403"""

        @HasPermission("view-View", app_name="ops-analysis")
        def list_view(request):
            return SimpleNamespace(status_code=200)

        user = MockUser(
            username="webuser_noperm",
            roles=[],
            permission={},
            is_superuser=False,
        )

        request = _make_request(user, api_pass=False)  # Web Token

        with patch.object(WebUtils, "response_403") as mock_403:
            mock_403.return_value = SimpleNamespace(status_code=403)
            response = list_view(request)

        # Web Token 用户无权限应该返回 403
        assert response.status_code == status.HTTP_403_FORBIDDEN
