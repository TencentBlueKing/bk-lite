"""技能工具与技能包更新：系统标签不可删，用户标签和分组可改。"""

import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.models import SkillPackage, SkillTools
from apps.opspilot.viewsets.llm_view import SkillPackageViewSet, SkillToolsViewSet

pytestmark = pytest.mark.django_db


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, username):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="zh-Hans",
        group_list=[{"id": 1, "name": "T1"}, {"id": 2, "name": "T2"}],
        roles=["normal"],
    )
    user.is_superuser = False
    user.save()
    user.permission = {"opspilot": {"tool_list-View", "tool_list-Add", "tool_list-Edit", "tool_list-Setting", "tool_list-Delete"}}
    return user


@pytest.fixture
def allow_team_instances(mocker):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"instance": [], "team": [1]},
    )
    mocker.patch(
        "apps.core.utils.serializers.get_permission_rules",
        return_value={"instance": [], "team": [1]},
    )


def _put(viewset, user, pk, payload):
    factory = APIRequestFactory()
    request = factory.put("/", payload, format="json")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return viewset.as_view({"put": "update"})(request, pk=pk)


def _post(viewset, user, payload):
    factory = APIRequestFactory()
    request = factory.post("/", payload, format="json")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return viewset.as_view({"post": "create"})(request)


def test_builtin_tool_update_keeps_system_tags_and_name(allow_team_instances):
    tool = SkillTools.objects.create(
        name="mysql",
        description="MySQL",
        is_build_in=True,
        team=[1],
        system_tags=["database"],
        user_tags=[],
        tags=["other"],
        params={"url": "langchain:mysql", "name": "mysql", "kwargs": []},
    )
    user = _user(username="tool_editor")
    rejected = _put(
        SkillToolsViewSet,
        user,
        tool.id,
        {
            "name": "hacked",
            "description": "changed",
            "team": [1, 2],
            "user_tags": ["值班"],
            "system_tags": [],
        },
    )
    assert rejected.status_code == 400
    tool.refresh_from_db()
    assert tool.name == "mysql"
    assert tool.description == "MySQL"
    assert tool.system_tags == ["database"]
    assert tool.user_tags == []
    assert tool.team == [1]

    accepted = _put(
        SkillToolsViewSet,
        user,
        tool.id,
        {
            "name": "hacked",
            "description": "changed",
            "team": [1, 2],
            "user_tags": ["  值班  ", "值班", ""],
            "system_tags": ["database"],
            "params": {"url": "http://evil", "name": "hacked", "kwargs": []},
        },
    )
    assert accepted.status_code == 200
    tool.refresh_from_db()
    assert tool.name == "mysql"
    assert tool.description == "MySQL"
    assert tool.params["url"] == "langchain:mysql"
    assert tool.system_tags == ["database"]
    assert tool.user_tags == ["值班"]
    assert tool.team == [1, 2]
    assert _body(accepted)["system_tags"] == ["database"]
    assert _body(accepted)["user_tags"] == ["值班"]


def test_mcp_tags_are_optional_user_tags(allow_team_instances):
    user = _user(username="mcp_editor")
    created = _post(
        SkillToolsViewSet,
        user,
        {
            "name": "docs-mcp",
            "description": "文档检索",
            "team": [1],
            "tags": ["search", "general", "search", "  "],
            "is_build_in": False,
            "params": {"url": "https://mcp.example.com", "name": "docs-mcp", "kwargs": []},
        },
    )
    assert created.status_code == 201
    tool = SkillTools.objects.get(name="docs-mcp")
    assert tool.system_tags == []
    assert tool.user_tags == ["search", "general"]

    cleared = _put(
        SkillToolsViewSet,
        user,
        tool.id,
        {
            "name": "docs-mcp",
            "description": "文档检索",
            "team": [1],
            "user_tags": [],
        },
    )
    assert cleared.status_code == 200
    tool.refresh_from_db()
    assert tool.user_tags == []
    assert tool.system_tags == []

    added = _put(
        SkillToolsViewSet,
        user,
        tool.id,
        {
            "name": "docs-mcp-renamed",
            "description": "文档检索已改",
            "team": [1],
            "user_tags": ["检索"],
        },
    )
    assert added.status_code == 200
    tool.refresh_from_db()
    assert tool.name == "docs-mcp-renamed"
    assert tool.description == "文档检索已改"
    assert tool.user_tags == ["检索"]


def test_builtin_skill_package_update_rejects_system_tag_removal(allow_team_instances):
    pkg = SkillPackage.objects.create(
        package_id="kubernetes-configuration",
        name="Kubernetes Specialist",
        version="1.1.1",
        description="desc",
        category="infrastructure",
        skill_markdown="body",
        domain="domain.com",
        team=[1],
        is_build_in=True,
        source_type="builtin",
        system_tags=["container"],
        user_tags=[],
    )
    user = _user(username="pkg_editor")
    rejected = _put(
        SkillPackageViewSet,
        user,
        pkg.id,
        {
            "package_id": "kubernetes-configuration",
            "name": "hacked",
            "version": "1.1.1",
            "description": "changed",
            "category": "other",
            "skill_markdown": "new body",
            "team": [2],
            "user_tags": ["值班"],
            "system_tags": [],
        },
    )
    assert rejected.status_code == 400
    pkg.refresh_from_db()
    assert pkg.name == "Kubernetes Specialist"
    assert pkg.system_tags == ["container"]
    assert pkg.user_tags == []

    accepted = _put(
        SkillPackageViewSet,
        user,
        pkg.id,
        {
            "package_id": "kubernetes-configuration",
            "name": "hacked",
            "version": "1.1.1",
            "description": "changed",
            "category": "other",
            "skill_markdown": "new body",
            "team": [2],
            "user_tags": ["  值班  ", ""],
            "system_tags": ["container"],
        },
    )
    assert accepted.status_code == 200
    pkg.refresh_from_db()
    assert pkg.name == "Kubernetes Specialist"
    assert pkg.description == "desc"
    assert pkg.category == "infrastructure"
    assert pkg.skill_markdown == "body"
    assert pkg.system_tags == ["container"]
    assert pkg.user_tags == ["值班"]
    assert pkg.team == [2]


def test_imported_skill_package_tags_can_be_cleared(allow_team_instances):
    pkg = SkillPackage.objects.create(
        package_id="local-runbook",
        name="Runbook",
        version="0.1.0",
        description="desc",
        category="ops",
        skill_markdown="body",
        domain="domain.com",
        team=[1],
        is_build_in=False,
        source_type="zip",
        system_tags=[],
        user_tags=["旧标签"],
    )
    user = _user(username="pkg_user")
    cleared = _put(
        SkillPackageViewSet,
        user,
        pkg.id,
        {
            "package_id": "local-runbook",
            "name": "hacked",
            "version": "0.1.0",
            "description": "desc",
            "skill_markdown": "new body",
            "team": [1],
            "user_tags": [],
        },
    )
    assert cleared.status_code == 200
    pkg.refresh_from_db()
    assert pkg.name == "Runbook"
    assert pkg.skill_markdown == "body"
    assert pkg.user_tags == []
    assert pkg.system_tags == []

    added = _put(
        SkillPackageViewSet,
        user,
        pkg.id,
        {
            "package_id": "local-runbook",
            "name": "Runbook",
            "version": "0.1.0",
            "description": "desc",
            "team": [1],
            "user_tags": ["值班", "值班", " "],
        },
    )
    assert added.status_code == 200
    pkg.refresh_from_db()
    assert pkg.user_tags == ["值班"]
