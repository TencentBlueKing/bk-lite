"""运营分析目录树 BDD（中文 Gherkin）。

对照 spec/prd/运营分析·目录：
- 层级 ≤ 3；
- (name, parent) 联合唯一；
- build_in_key 唯一；
- 级联删除子目录；
- get_level 计算。

2 happy + 5 corner（7 场景）。
"""

from pathlib import Path

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.db import IntegrityError, transaction
from pytest_bdd import given, parsers, scenarios, then, when

from apps.operation_analysis.models.models import Directory

FEATURE = str(Path(__file__).parent / "directory.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"result": None, "error": None}


@pytest.fixture
def _dir_db(db):
    return db


def _groups_list(raw: str) -> list[int]:
    return [int(g.strip()) for g in raw.split(",") if g.strip()]


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.re(r'已存在目录 "(?P<name>[^"]+)" 无父目录 groups=\[(?P<groups>[^\]]*)\]'))
def _seed_root(_dir_db, name, groups):
    Directory.objects.create(name=name, groups=_groups_list(groups))


@given(parsers.re(r'已存在目录 "(?P<name>[^"]+)" parent="(?P<parent>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _seed_child(_dir_db, name, parent, groups):
    Directory.objects.create(
        name=name, groups=_groups_list(groups), parent=Directory.objects.get(name=parent)
    )


@given(parsers.re(
    r'已存在内置目录 name="(?P<name>[^"]+)" build_in_key="(?P<key>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'
))
def _seed_builtin(_dir_db, name, key, groups):
    Directory.objects.create(
        name=name, groups=_groups_list(groups), is_build_in=True, build_in_key=key,
    )


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.re(r'我创建目录 name="(?P<name>[^"]+)" parent=None groups=\[(?P<groups>[^\]]*)\]'))
def _create_root(ctx, _dir_db, name, groups):
    try:
        Directory.objects.create(name=name, groups=_groups_list(groups))
        ctx["result"] = "ok"
    except (IntegrityError, DjangoValidationError, DRFValidationError) as exc:
        ctx["error"] = exc


@when(parsers.re(r'我创建目录 name="(?P<name>[^"]+)" parent="(?P<parent>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _create_child(ctx, _dir_db, name, parent, groups):
    try:
        Directory.objects.create(
            name=name, groups=_groups_list(groups),
            parent=Directory.objects.get(name=parent),
        )
        ctx["result"] = "ok"
    except (IntegrityError, DjangoValidationError, DRFValidationError) as exc:
        ctx["error"] = exc


@when(parsers.re(r'我尝试创建目录 name="(?P<name>[^"]+)" parent="(?P<parent>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _try_create_child(ctx, _dir_db, name, parent, groups):
    try:
        with transaction.atomic():
            Directory.objects.create(
                name=name, groups=_groups_list(groups),
                parent=Directory.objects.get(name=parent),
            )
    except (IntegrityError, DjangoValidationError, DRFValidationError) as exc:
        ctx["error"] = exc


@when(parsers.re(
    r'我尝试创建内置目录 name="(?P<name>[^"]+)" build_in_key="(?P<key>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'
))
def _try_create_builtin(ctx, _dir_db, name, key, groups):
    try:
        with transaction.atomic():
            Directory.objects.create(
                name=name, groups=_groups_list(groups),
                is_build_in=True, build_in_key=key,
            )
    except IntegrityError as exc:
        ctx["error"] = exc


@when(parsers.parse('我删除目录 "{name}"'))
def _delete_dir(name):
    Directory.objects.get(name=name).delete()


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then("目录创建应当成功")
def _ok(ctx):
    assert ctx["error"] is None, ctx["error"]


@then(parsers.parse('目录 "{name}" 的层级应当为 {level:d}'))
def _level(name, level):
    assert Directory.objects.get(name=name).get_level() == level


@then("应当抛出唯一约束异常")
def _unique_violation(ctx):
    assert isinstance(ctx["error"], IntegrityError), ctx["error"]


@then("应当抛出层级超限异常")
def _level_violation(ctx):
    assert isinstance(ctx["error"], (DjangoValidationError, DRFValidationError)), ctx["error"]
    assert "exceed 3" in str(ctx["error"]) or "层级" in str(ctx["error"])  # noqa: PLR1714


@then(parsers.parse('数据库中不应再存在目录 "{name}"'))
def _db_absent(name):
    assert not Directory.objects.filter(name=name).exists()
