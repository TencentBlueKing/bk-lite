"""补齐登录模块显示名的内置与自定义分支。"""

from types import SimpleNamespace

import pytest

from apps.system_mgmt.serializers.login_module_serializer import (
    LoginModuleSerializer,
)


pytestmark = pytest.mark.unit


def test_login_module_display_name_translates_only_builtin_modules():
    serializer = LoginModuleSerializer()

    assert str(
        serializer.get_display_name(
            SimpleNamespace(is_build_in=True, name="Local")
        )
    ) == "Local"
    assert serializer.get_display_name(
        SimpleNamespace(is_build_in=False, name="Corporate SSO")
    ) == "Corporate SSO"
