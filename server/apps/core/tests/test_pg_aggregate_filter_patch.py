"""
聚合 ``FILTER (WHERE ...)`` 降级补丁的回归测试。

锁定三件事：
1. 共享入口把 Django postgresql features 的开关关掉，且幂等；
2. 关掉后 Django 用 postgresql 编译器生成的 SQL 不再含 ``FILTER (``，而是 ``CASE WHEN``；
3. vastbase / kingbase / gaussdb 三个补丁都真的调用了该入口。
"""

import logging

import pytest
from django.db import connections
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.backends.postgresql.features import DatabaseFeatures
from django.db.models import Count, Max, Q

from apps.core.db_patches import gaussdb, kingbase, vastbase
from apps.core.db_patches.pg_aggregate_filter import disable_aggregate_filter_clause
from apps.system_mgmt.models.app import App


@pytest.fixture
def pg_features(monkeypatch):
    """每个用例从 Django 默认值 True 出发，避免用例间串扰。"""
    monkeypatch.setattr(DatabaseFeatures, "supports_aggregate_filter_clause", True)
    return DatabaseFeatures


@pytest.fixture
def pg_connection():
    """不建连的 postgresql DatabaseWrapper：只用它的 ops / features 做 SQL 编译。"""
    settings_dict = {**connections["default"].settings_dict, "ENGINE": "django.db.backends.postgresql"}
    return DatabaseWrapper(settings_dict, alias="pg_dry_run")


def _compile(pg_connection):
    scope = Q(id__gt=0)
    queryset = App.objects.annotate(
        scoped_count=Count("id", filter=scope, distinct=True),
        scoped_last=Max("id", filter=scope),
    )
    sql, _params = queryset.query.get_compiler(connection=pg_connection).as_sql()
    return sql


# ============================================================
# 1. 共享入口
# ============================================================


def test_disable_turns_off_pg_feature_flag(pg_features):
    assert pg_features.supports_aggregate_filter_clause is True

    disable_aggregate_filter_clause()

    assert pg_features.supports_aggregate_filter_clause is False


def test_disable_covers_extra_feature_classes(pg_features):
    """第三方后端子类自行覆写了开关时，显式传入也要被关掉。"""

    class ThirdPartyFeatures(pg_features):
        supports_aggregate_filter_clause = True

    patched = disable_aggregate_filter_clause(ThirdPartyFeatures)

    assert ThirdPartyFeatures.supports_aggregate_filter_clause is False
    assert patched == (pg_features, ThirdPartyFeatures)


def test_disable_is_idempotent(pg_features):
    disable_aggregate_filter_clause()
    disable_aggregate_filter_clause()

    assert pg_features.supports_aggregate_filter_clause is False


def test_disable_logs_stable_template_with_lazy_count(pg_features, caplog):
    """生命周期 INFO：稳定模板 + 独立参数，渲染结果只含被关掉的 features 类数量。"""

    class ThirdPartyFeatures(pg_features):
        supports_aggregate_filter_clause = True

    with caplog.at_level(logging.INFO, logger="app"):
        patched = disable_aggregate_filter_clause(ThirdPartyFeatures)

    records = [r for r in caplog.records if r.name == "app" and "aggregate FILTER clause disabled" in r.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.msg == "postgresql aggregate FILTER clause disabled, falling back to CASE WHEN (%d feature classes)"
    assert record.args == (len(patched),)
    assert record.getMessage() == "postgresql aggregate FILTER clause disabled, falling back to CASE WHEN (2 feature classes)"
    assert record.exc_info is None


# ============================================================
# 2. 生成的 SQL
# ============================================================


def test_default_pg_backend_emits_filter_clause(pg_features, pg_connection):
    """基线：未打补丁时 Django 确实生成 FILTER 子句（即 Vastbase 上会报错的形态）。"""
    sql = _compile(pg_connection)

    assert "FILTER (WHERE" in sql
    assert "CASE WHEN" not in sql


def test_patched_backend_falls_back_to_case_when(pg_features, pg_connection):
    """打补丁后 Count(distinct)/Max 都改写为 CASE WHEN，SQL 中不再出现 FILTER。"""
    disable_aggregate_filter_clause()

    sql = _compile(pg_connection)

    assert "FILTER (" not in sql
    assert sql.count("CASE WHEN") == 2
    assert "COUNT(DISTINCT CASE WHEN" in sql
    assert "MAX(CASE WHEN" in sql


# ============================================================
# 3. 各兼容库补丁接线
# ============================================================


@pytest.mark.parametrize(
    "module",
    [vastbase, kingbase, gaussdb],
    ids=["vastbase", "kingbase", "gaussdb"],
)
def test_each_pg_compat_patch_disables_filter_clause(pg_features, module):
    module._patch_aggregate_filter_clause()

    assert pg_features.supports_aggregate_filter_clause is False


def test_gaussdb_patch_entry_calls_aggregate_filter(monkeypatch):
    """gaussdb.patch() 走 CoreConfig.ready() 的分发入口，必须把该补丁挂上。"""
    calls = []
    monkeypatch.setattr(gaussdb, "_patch_aggregate_filter_clause", lambda: calls.append("aggregate_filter"))

    gaussdb.patch()

    assert calls == ["aggregate_filter"]


def test_gaussdb_tolerates_missing_cw_cornerstone(monkeypatch):
    """本地未安装 cw_cornerstone 时不应报错，只补 Django 基类。"""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("cw_cornerstone"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert gaussdb._gaussdb_feature_classes() == ()


def test_gaussdb_passes_third_party_features_when_available(monkeypatch):
    """cw_cornerstone 存在时，其 GaussDB features 子类也要被显式关掉。"""
    third_party = type("DatabaseFeatures", (DatabaseFeatures,), {"supports_aggregate_filter_clause": True})
    monkeypatch.setattr(gaussdb, "_gaussdb_feature_classes", lambda: (third_party,))
    monkeypatch.setattr(DatabaseFeatures, "supports_aggregate_filter_clause", True)

    gaussdb._patch_aggregate_filter_clause()

    assert third_party.supports_aggregate_filter_clause is False
    assert DatabaseFeatures.supports_aggregate_filter_clause is False


def test_kingbase_apply_early_patches_wires_aggregate_filter(monkeypatch):
    monkeypatch.setattr(kingbase, "_patches_applied", False)
    calls = []
    for name in (
        "_patch_introspection_pipe_concat",
        "_patch_pattern_ops_pipe_concat",
        "_patch_psycopg3_timestamptz_missing_tz",
        "_patch_psycopg3_kingbase_datetime_oids",
        "_patch_aggregate_filter_clause",
    ):
        monkeypatch.setattr(kingbase, name, (lambda n: (lambda: calls.append(n)))(name))

    kingbase.apply_early_patches()
    kingbase.apply_early_patches()

    assert calls[-1] == "_patch_aggregate_filter_clause"
    assert len(calls) == 5
