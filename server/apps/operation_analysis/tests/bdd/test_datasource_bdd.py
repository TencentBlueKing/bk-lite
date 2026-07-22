"""运营分析数据源 BDD（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-运营分析-管理.md：
- NameSpace 凭据加解密 + name 唯一；
- DataSourceAPIModel (name, rest_api) 联合唯一 + 团队过滤；
- DataSourceTag name 唯一；
- 空密码不触发加密。

3 happy + 5 corner（8 场景）。
"""

import pytest
from django.db import IntegrityError, transaction
from pytest_bdd import given, parsers, scenarios, then, when

from apps.operation_analysis.filters.base_filters import GroupPermissionMixin
from apps.operation_analysis.models.datasource_models import (
    DataSourceAPIModel,
    DataSourceTag,
    NameSpace,
)

FEATURE = "apps/operation_analysis/tests/bdd/datasource.feature"
from pathlib import Path
scenarios(str(Path(__file__).parent / "datasource.feature"))


@pytest.fixture
def ctx():
    return {"result": None, "error": None}


@pytest.fixture
def _ds_db(db):
    return db


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse('已存在 NameSpace "{name}"'))
def _seed_ns(_ds_db, name):
    ns = NameSpace(name=name, account="acc", domain="127.0.0.1:4222")
    ns.set_password("orig")
    ns.save()


@given(parsers.parse('已存在 NameSpace "{name}" password="{password}"'))
def _seed_ns_with_pwd(_ds_db, name, password):
    ns = NameSpace(name=name, account="acc", domain="127.0.0.1:4222")
    ns.set_password(password)
    ns.save()


@given(parsers.re(r'已存在数据源 "(?P<name>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _seed_ds(_ds_db, name, groups):
    DataSourceAPIModel.objects.create(
        name=name, rest_api=f"/api/{name}",
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
    )


@given(parsers.re(r'已存在数据源 name="(?P<name>[^"]+)" rest_api="(?P<api>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _seed_ds_full(_ds_db, name, api, groups):
    DataSourceAPIModel.objects.create(
        name=name, rest_api=api,
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
    )


@given(parsers.parse('已存在 DataSourceTag tag_id="{tag_id}" name="{name}"'))
def _seed_tag(_ds_db, tag_id, name):
    DataSourceTag.objects.create(tag_id=tag_id, name=name)


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.parse('我创建 NameSpace name="{name}" account="{account}" password="{password}" domain="{domain}"'))
def _create_ns(ctx, _ds_db, name, account, password, domain):
    try:
        ns = NameSpace(name=name, account=account, domain=domain)
        ns.set_password(password)
        ns.save()
        ctx["result"] = ns
    except IntegrityError as exc:
        ctx["error"] = exc


@when(parsers.parse('我创建 NameSpace name="{name}" account="{account}" password="" domain="{domain}"'))
def _create_ns_empty(ctx, _ds_db, name, account, domain):
    ns = NameSpace(name=name, account=account, domain=domain)
    ns.set_password("")
    ns.save()
    ctx["result"] = ns


@when(parsers.parse('我尝试创建 NameSpace name="{name}" account="{account}" password="{password}" domain="{domain}"'))
def _try_create_ns(ctx, name, account, password, domain):
    try:
        with transaction.atomic():
            ns = NameSpace(name=name, account=account, domain=domain)
            ns.set_password(password)
            ns.save()
        ctx["result"] = ns
    except IntegrityError as exc:
        ctx["error"] = exc


@when(parsers.re(
    r'我创建 DataSourceAPIModel name="(?P<name>[^"]+)" rest_api="(?P<api>[^"]+)" '
    r'groups=\[(?P<groups>[^\]]*)\] 并关联 NameSpace "(?P<ns>[^"]+)"'
))
def _create_ds(ctx, _ds_db, name, api, groups, ns):
    ds = DataSourceAPIModel.objects.create(
        name=name, rest_api=api,
        groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
    )
    namespace = NameSpace.objects.get(name=ns)
    ds.namespaces.add(namespace)
    ctx["result"] = ds


@when(parsers.re(r'我尝试创建数据源 name="(?P<name>[^"]+)" rest_api="(?P<api>[^"]+)" groups=\[(?P<groups>[^\]]*)\]'))
def _try_create_ds(ctx, name, api, groups):
    try:
        with transaction.atomic():
            DataSourceAPIModel.objects.create(
                name=name, rest_api=api,
                groups=[int(g.strip()) for g in groups.split(",") if g.strip()],
            )
    except IntegrityError as exc:
        ctx["error"] = exc


@when(parsers.parse("我以 current_team={team:d} 调用 apply_group_filter"))
def _apply_filter(ctx, team):
    qs = DataSourceAPIModel.objects.all()
    ctx["result"] = GroupPermissionMixin.apply_group_filter(qs, team)


@when(parsers.parse('我对 "{name}" 调用 set_password("{new_pwd}") 并保存'))
def _rotate_pwd(name, new_pwd):
    ns = NameSpace.objects.get(name=name)
    ns.set_password(new_pwd)
    ns.save()


@when(parsers.parse('我尝试创建 DataSourceTag tag_id="{tag_id}" name="{name}"'))
def _try_create_tag(ctx, tag_id, name):
    try:
        with transaction.atomic():
            DataSourceTag.objects.create(tag_id=tag_id, name=name)
    except IntegrityError as exc:
        ctx["error"] = exc


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then("NameSpace 创建应当成功")
@then("数据源创建应当成功")
def _no_error(ctx):
    assert ctx["error"] is None, ctx["error"]


@then(parsers.parse('数据库中存在 NameSpace name="{name}"'))
def _db_ns(name):
    assert NameSpace.objects.filter(name=name).exists()


@then(parsers.parse('decrypt_password 应当能还原为 "{plain}"'))
def _decrypt(plain):
    ns = NameSpace.objects.order_by("-id").first()
    assert ns.decrypt_password == plain


@then(parsers.parse("数据源关联的 NameSpace 数量应当为 {n:d}"))
def _ds_ns_count(ctx, n):
    assert ctx["result"].namespaces.count() == n


@then(parsers.parse('结果数据源应当恰好包含 "{name}"'))
def _filter_result(ctx, name):
    actual = set(ctx["result"].values_list("name", flat=True))
    assert actual == {name}, actual


@then("应当抛出唯一约束异常")
def _unique_violation(ctx):
    assert isinstance(ctx["error"], IntegrityError), ctx["error"]


@then(parsers.parse('数据库中 "{name}" 的 password 字段为空'))
def _empty_pwd(name):
    assert NameSpace.objects.get(name=name).password == ""
