"""运营分析画布 BDD（中文 Gherkin）。

对照 spec/prd/运营分析·画布：
- Dashboard CRUD + 目录归属；
- name 唯一约束；
- build_in_key 唯一约束；
- 目录删除级联画布；
- 团队过滤。

2 happy + 4 corner（6 场景）。
"""

from pathlib import Path

import pytest
from django.db import IntegrityError, transaction
from pytest_bdd import given, parsers, scenarios, then, when

from apps.operation_analysis.filters.base_filters import GroupPermissionMixin
from apps.operation_analysis.models.models import Dashboard, Directory

FEATURE = str(Path(__file__).parent / "canvas.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"result": None, "error": None}


@pytest.fixture
def _canvas_db(db):
    return db


@given(parsers.re(r'已存在目录 "(?P<name>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _seed_dir(_canvas_db, name, groups):
    Directory.objects.create(
        name=name, groups=[int(g.strip()) for g in groups.split(",") if g.strip()]
    )


@given(parsers.re(r'已存在 Dashboard "(?P<name>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _seed_dash(_canvas_db, name, groups):
    Dashboard.objects.create(
        name=name, groups=[int(g.strip()) for g in groups.split(",") if g.strip()]
    )


@given(parsers.re(
    r'已存在 Dashboard "(?P<name>[^"]+)" groups=\[(?P<groups>[^\]]*)\] 归属目录 "(?P<dir_name>[^"]+)"'
))
def _seed_dash_in_dir(_canvas_db, name, groups, dir_name):
    Dashboard.objects.create(
        name=name,
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
        directory=Directory.objects.get(name=dir_name),
    )


@given(parsers.re(
    r'已存在内置 Dashboard "(?P<name>[^"]+)" build_in_key="(?P<key>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'
))
def _seed_builtin(_canvas_db, name, key, groups):
    Dashboard.objects.create(
        name=name, is_build_in=True, build_in_key=key,
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
    )


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.re(
    r'我创建 Dashboard name="(?P<name>[^"]+)" desc="(?P<desc>[^"]*)" 归属目录 "(?P<dir_name>[^"]+)" '
    r'groups=\[(?P<groups>[^\]]*)\]'
))
def _create_dash_in_dir(ctx, _canvas_db, name, desc, dir_name, groups):
    Dashboard.objects.create(
        name=name, desc=desc,
        directory=Directory.objects.get(name=dir_name),
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
    )
    ctx["result"] = "ok"


@when(parsers.re(
    r'我创建 Dashboard name="(?P<name>[^"]+)" desc="(?P<desc>[^"]*)" 不归属任何目录 groups=\[(?P<groups>[^\]]*)\]'
))
def _create_dash_no_dir(ctx, _canvas_db, name, desc, groups):
    Dashboard.objects.create(
        name=name, desc=desc,
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
    )
    ctx["result"] = "ok"


@when(parsers.re(
    r'我尝试创建 Dashboard name="(?P<name>[^"]+)" desc="(?P<desc>[^"]*)" groups=\[(?P<groups>[^\]]*)\]'
))
def _try_create_dash(ctx, _canvas_db, name, desc, groups):
    try:
        with transaction.atomic():
            Dashboard.objects.create(
                name=name, desc=desc,
                groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
            )
    except IntegrityError as exc:
        ctx["error"] = exc


@when(parsers.re(
    r'我尝试创建内置 Dashboard "(?P<name>[^"]+)" build_in_key="(?P<key>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'
))
def _try_create_builtin(ctx, _canvas_db, name, key, groups):
    try:
        with transaction.atomic():
            Dashboard.objects.create(
                name=name, is_build_in=True, build_in_key=key,
                groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
            )
    except IntegrityError as exc:
        ctx["error"] = exc


@when(parsers.parse("我以 current_team={team:d} 调用 apply_group_filter"))
def _apply_filter(ctx, team):
    qs = Dashboard.objects.all()
    ctx["result"] = GroupPermissionMixin.apply_group_filter(qs, team)


@when(parsers.parse('我删除目录 "{name}"'))
def _delete_dir(name):
    Directory.objects.get(name=name).delete()


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then("画布创建应当成功")
def _ok(ctx):
    assert ctx["error"] is None, ctx["error"]


@then(parsers.parse('数据库中存在 Dashboard name="{name}"'))
def _db_exists(name):
    assert Dashboard.objects.filter(name=name).exists()


@then(parsers.parse('结果画布应当恰好包含 "{name}"'))
def _filter_result(ctx, name):
    actual = set(ctx["result"].values_list("name", flat=True))
    assert actual == {name}, actual


@then("应当抛出唯一约束异常")
def _unique_violation(ctx):
    assert isinstance(ctx["error"], IntegrityError), ctx["error"]


@then(parsers.parse('数据库中不应再存在 Dashboard "{name}"'))
def _db_absent(name):
    assert not Dashboard.objects.filter(name=name).exists()


@then(parsers.parse('Dashboard "{name}" 的 directory 应当为 None'))
def _no_dir(name):
    assert Dashboard.objects.get(name=name).directory is None
