"""_check_permission：全局超管之后按端点 permission_app 认 {app}--admin。"""

import pytest

from apps.core.openapi.dispatcher import _check_permission
from apps.core.openapi.identity import CREDENTIAL_API_TOKEN, CallerIdentity
from apps.core.openapi.registry import Endpoint

pytestmark = pytest.mark.unit


def _endpoint(**overrides):
    params = dict(
        service="alerts",
        sub_path="list",
        method="GET",
        func=lambda **kwargs: None,
        serializer_class=object,
        inject="team_list",
        permission="Alarms-View",
        permission_app="alarm",
    )
    params.update(overrides)
    return Endpoint(**params)


def _identity(**overrides):
    params = dict(
        user="leviathan",
        domain="domain.com",
        credential_type=CREDENTIAL_API_TOKEN,
        is_superuser=False,
        permission={},
        roles=[],
    )
    params.update(overrides)
    return CallerIdentity(**params)


def test_app_admin_with_empty_menus_passes_same_app():
    identity = _identity(roles=["alarm--admin"], permission={})
    assert _check_permission(identity, _endpoint()) is True


def test_other_app_admin_does_not_pass():
    identity = _identity(roles=["cmdb--admin"], permission={})
    assert _check_permission(identity, _endpoint()) is False


def test_empty_roles_and_empty_menus_still_denied():
    assert _check_permission(_identity(), _endpoint()) is False


def test_menu_intersection_still_required_without_app_admin():
    identity = _identity(roles=["alarm--normal"], permission={"alarm": {"Alarms-View"}})
    assert _check_permission(identity, _endpoint()) is True
    denied = _identity(roles=["alarm--normal"], permission={"alarm": {"Alarms-Edit"}})
    assert _check_permission(denied, _endpoint()) is False


def test_platform_superuser_still_bypasses_menus():
    identity = _identity(is_superuser=True, roles=[], permission={})
    assert _check_permission(identity, _endpoint()) is True


def test_undeclared_permission_skips_app_admin():
    endpoint = _endpoint(permission="", permission_app="")
    assert _check_permission(_identity(roles=[]), endpoint) is True
