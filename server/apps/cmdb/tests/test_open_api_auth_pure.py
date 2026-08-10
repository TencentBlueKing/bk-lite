from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.cmdb.open_api.auth import CMDBOpenAPIContext
from apps.cmdb.open_api.errors import CMDBOpenAPIError


def _request(*, api_pass=True, groups=None, permissions=None):
    user = SimpleNamespace(
        username="api-user",
        domain="domain.com",
        group_list=groups or [{"id": 7}],
        roles=["cmdb-reader"],
        permission={"cmdb": set(permissions or [])},
        is_superuser=False,
        locale="zh-CN",
    )
    return SimpleNamespace(api_pass=api_pass, user=user, COOKIES={"include_children": "1"})


def test_context_rejects_non_api_secret_request():
    with pytest.raises(CMDBOpenAPIError) as exc:
        CMDBOpenAPIContext.from_request(_request(api_pass=False))
    assert exc.value.status_code == 403
    assert exc.value.code == "cmdb.auth.api_secret_required"


def test_context_uses_only_secret_bound_team_and_ignores_child_cookie():
    context = CMDBOpenAPIContext.from_request(_request(groups=[{"id": 7}]))
    assert context.team_id == 7
    assert context.user_groups == [{"id": 7}]


@patch("apps.cmdb.open_api.auth.get_permission_rules")
def test_permission_map_is_fail_closed_and_never_includes_children(mock_rules):
    mock_rules.return_value = {}
    context = CMDBOpenAPIContext.from_request(_request())
    result = context.permission_map("host", "instances")
    assert set(result) == {7}
    assert result[7]["inst_names"]
    mock_rules.assert_called_once_with(
        user=context.user,
        current_team=7,
        app_name="cmdb",
        permission_key="instances.host",
        include_children=False,
    )
