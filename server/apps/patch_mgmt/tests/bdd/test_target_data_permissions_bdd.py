from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework import status

from apps.patch_mgmt.models import PatchTarget
from apps.system_mgmt.models import Group


FEATURE = str(Path(__file__).parent / "target_data_permissions.feature")
scenarios(FEATURE)

pytestmark = [pytest.mark.bdd, pytest.mark.django_db]

TARGET_URL = "/api/v1/patch_mgmt/api/patch_target/"


@pytest.fixture
def ctx(api_client, authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.roles = []
    authenticated_user.permission = {"patch": {"patch_target-View"}}
    return {
        "client": api_client,
        "user": authenticated_user,
        "targets": {},
        "rules": {"team": [], "instance": []},
    }


@given(parsers.parse("当前用户属于团队 {team_id:d}"))
def given_user_group(ctx, team_id):
    group, _ = Group.objects.update_or_create(
        id=team_id,
        defaults={"name": f"Team {team_id}", "parent_id": 0},
    )
    ctx["user"].group_list = [{"id": group.id, "name": group.name}]
    ctx["user"].group_tree = [
        {"id": group.id, "name": group.name, "subGroups": []}
    ]


@given(parsers.parse("当前团队选择为 {team_id:d}"))
def given_current_team(ctx, team_id):
    ctx["client"].cookies["current_team"] = str(team_id)


@given("未选择当前团队")
def given_no_current_team(ctx):
    ctx["client"].cookies.pop("current_team", None)


@given(parsers.parse("当前团队包含子组织 {team_id:d}"))
def given_include_child_team(ctx, team_id):
    Group.objects.update_or_create(
        id=team_id,
        defaults={"name": f"Team {team_id}", "parent_id": 1},
    )
    ctx["user"].group_tree[0]["subGroups"] = [
        {"id": team_id, "name": f"Team {team_id}", "subGroups": []}
    ]
    ctx["client"].cookies["include_children"] = "1"


@given(parsers.parse('存在目标"{name}"属于团队 {team_id:d}'))
def given_target(ctx, name, team_id):
    target = PatchTarget.objects.create(
        name=name,
        ip=f"10.{team_id}.0.{len(ctx['targets']) + 10}",
        team=[team_id],
    )
    ctx["targets"][name] = target


@given(parsers.parse("数据权限授予整个团队 {team_id:d}"))
def given_team_rule(ctx, team_id):
    ctx["rules"] = {"team": [team_id], "instance": []}


@given("数据权限为空")
def given_no_rule(ctx):
    ctx["rules"] = {"team": [], "instance": []}


@given(parsers.parse('数据权限只授予目标"{name}"'))
def given_instance_rule(ctx, name):
    target = ctx["targets"][name]
    ctx["rules"] = {
        "team": [],
        "instance": [{"id": target.id, "permission": ["View", "Operate"]}],
    }


@when("用户查询补丁目标列表")
def when_query_targets(ctx, mocker):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value=ctx["rules"],
    )
    ctx["response"] = ctx["client"].get(TARGET_URL)


@then("请求应当成功")
def then_success(ctx):
    assert ctx["response"].status_code == status.HTTP_200_OK


@then("请求应当被拒绝")
def then_forbidden(ctx):
    assert ctx["response"].status_code == status.HTTP_403_FORBIDDEN


def _result_names(response):
    payload = response.data
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    return sorted(row["name"] for row in rows)


@then(parsers.parse('返回目标名称应为"{names}"'))
def then_target_names(ctx, names):
    assert _result_names(ctx["response"]) == sorted(names.split(","))


@then("返回目标列表应为空")
def then_empty(ctx):
    assert _result_names(ctx["response"]) == []
