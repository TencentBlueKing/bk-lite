"""运营分析 BDD：GroupPermissionMixin 团队权限与 queryset 过滤（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-运营分析-运营分析.md：数据源/画布按组织分组隔离，当前团队 cookie 与 user 维度共同决定可见范围。
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.operation_analysis.filters.base_filters import GroupPermissionMixin
from apps.operation_analysis.models.models import Directory

FEATURE = str(Path(__file__).parent / "group_permission.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"request": None, "ok": None, "team": None, "qs_result": None, "source_count": None}


def _request(method="GET", current_team=None, get_params=None):
    cookies = {"current_team": current_team} if current_team is not None else {}
    return SimpleNamespace(
        method=method,
        GET=get_params or {},
        COOKIES=cookies,
        user=SimpleNamespace(username="testuser", group_list=[1]),
    )


# ---------- 假设 ----------

@given(parsers.parse('一个 GET 请求 current_team 为 "{team}"'))
def _req_with_team(ctx, team):
    ctx["request"] = _request(current_team=team)


@given("一个 GET 请求未携带 current_team")
def _req_without_team(ctx):
    ctx["request"] = _request(current_team=None)


@given("一个 GET 请求未携带 all_groups 参数")
def _req_no_all_groups(ctx):
    ctx["request"] = _request(get_params={})


@given(parsers.parse('一个 GET 请求 all_groups 参数为 "{value}"'))
def _req_with_all_groups(ctx, value):
    ctx["request"] = _request(get_params={"all_groups": value})


@given(parsers.re(r'存在目录 "(?P<name>[^"]+)" 隶属组 \[(?P<groups>[^\]]*)\]$'))
def _dir_exists(db, name, groups):
    group_ids = [int(g.strip()) for g in groups.split(",") if g.strip()]
    Directory.objects.create(name=name, groups=group_ids, created_by="testuser")


@given(parsers.re(r'存在目录 "(?P<name>[^"]+)" 隶属组 \[(?P<groups>[^\]]*)\]，创建人为 "(?P<creator>[^"]+)"'))
def _dir_exists_by(db, name, groups, creator):
    group_ids = [int(g.strip()) for g in groups.split(",") if g.strip()]
    Directory.objects.create(name=name, groups=group_ids, created_by=creator)


# ---------- 当 ----------

@when("我执行 validate_group_permission")
def _run_validate_group(ctx):
    ok, team = GroupPermissionMixin.validate_group_permission(ctx["request"])
    ctx["ok"] = ok
    ctx["team"] = team


@when("我执行 validate_all_groups_permission")
def _run_validate_all(ctx):
    ok, _team = GroupPermissionMixin.validate_all_groups_permission(ctx["request"])
    ctx["ok"] = ok


@when(parsers.parse("我使用 current_team {team:d} 执行 apply_group_filter"))
def _apply_filter_team(ctx, team):
    qs = Directory.objects.all()
    ctx["source_count"] = qs.count()
    ctx["qs_result"] = GroupPermissionMixin.apply_group_filter(qs, team)


@when("我使用 current_team None 执行 apply_group_filter")
def _apply_filter_none(ctx):
    qs = Directory.objects.all()
    ctx["source_count"] = qs.count()
    ctx["qs_result"] = GroupPermissionMixin.apply_group_filter(qs, None)


@when(parsers.parse('我使用 current_team {team:d} 与用户 "{username}" 执行 apply_group_filter'))
def _apply_filter_user(ctx, team, username):
    qs = Directory.objects.all()
    ctx["source_count"] = qs.count()
    user = SimpleNamespace(username=username, domain="domain.com")
    ctx["qs_result"] = GroupPermissionMixin.apply_group_filter(qs, team, user=user)


# ---------- 那么 ----------

@then(parsers.parse("校验应当通过，团队为 {team:d}"))
def _validation_succeed(ctx, team):
    assert ctx["ok"] is True
    assert ctx["team"] == team


@then("校验应当失败")
def _validation_fail(ctx):
    assert ctx["ok"] is False


@then("全组校验应当被拒绝")
def _all_groups_denied(ctx):
    assert ctx["ok"] is False


@then("全组校验应当通过")
def _all_groups_granted(ctx):
    assert ctx["ok"] is True


@then(parsers.re(r'结果目录应当恰好为 \[(?P<names>[^\]]*)\]'))
def _directories_eq(ctx, names):
    expected = {n.strip().strip('"') for n in names.split(",") if n.strip()}
    actual = set(ctx["qs_result"].values_list("name", flat=True))
    assert actual == expected, f"expected={expected} actual={actual}"


@then("结果目录数量应当等于源数量")
def _count_equal(ctx):
    assert ctx["qs_result"].count() == ctx["source_count"]
