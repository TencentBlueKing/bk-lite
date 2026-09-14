"""技能包列表权限码必须是 tool_list-*，不能写成 tools_list-*。"""

import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

pytestmark = pytest.mark.django_db


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, username, permissions):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["normal"],
    )
    user.is_superuser = False
    user.save()
    user.permission = {"opspilot": set(permissions)}
    return user


def _dispatch(viewset, action_name, *, user):
    factory = APIRequestFactory()
    request = factory.get("/")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return viewset.as_view({"get": action_name})(request)


@pytest.fixture
def allow_team_instances(mocker):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"instance": [], "team": [1]},
    )


class TestSkillPackageListPermissions:
    def test_tool_list_view_can_list(self, allow_team_instances):
        user = _user(username="pkg_tools", permissions={"tool_list-View"})
        resp = _dispatch(SkillPackageViewSet, "list", user=user)
        assert resp.status_code == 200

    def test_typo_tools_list_view_is_forbidden(self):
        user = _user(username="pkg_typo", permissions={"tools_list-View"})
        resp = _dispatch(SkillPackageViewSet, "list", user=user)
        assert resp.status_code == 403
        assert _body(resp).get("result") is False

    def test_unrelated_permission_is_forbidden(self):
        user = _user(username="pkg_deny", permissions={"bot_list-View"})
        resp = _dispatch(SkillPackageViewSet, "list", user=user)
        assert resp.status_code == 403
        assert _body(resp).get("result") is False
