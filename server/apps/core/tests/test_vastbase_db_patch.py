"""Vastbase G100 B 兼容模式补丁的行为回归测试。

覆盖 apps/core/db_patches/vastbase.py 的六类补丁。多数用例直接把 **Django 真实的
introspection SQL** 过一遍改写并断言结果，因此 Django 升级导致 SQL 结构变化时，
这里会先失败，而不是等到目标环境 migrate 才暴露。
"""

import datetime
from types import SimpleNamespace

import pytest
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.backends.postgresql.features import DatabaseFeatures
from django.db.backends.postgresql.introspection import DatabaseIntrospection
from django.db.backends.postgresql.operations import DatabaseOperations
from django.db.models.constants import OnConflict

from apps.core.db_patches import vastbase


class _RecordingCursor:
    """记录收到的 SQL，供断言改写结果；查询一律返回空集。"""

    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeConnection:
    """模拟 connection_created 信号里的 connection：只需支撑一次偏移探测查询。"""

    vendor = "postgresql"

    def __init__(self, offset_seconds, fail=False):
        self._offset_seconds = offset_seconds
        self._fail = fail

    def cursor(self):
        outer = self

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                if outer._fail:
                    raise RuntimeError("EXTRACT(TIMEZONE ...) unsupported")

            def fetchone(self):
                return (outer._offset_seconds,)

        return _Cursor()


@pytest.fixture
def introspection():
    return DatabaseIntrospection(SimpleNamespace())


# ============================================================
# 1. 版本门
# ============================================================


def test_minimum_database_version_is_disabled(monkeypatch):
    """Vastbase 上报 9.2.4，必须跳过 Django 的 >= 12 硬检查。"""
    monkeypatch.setattr(DatabaseFeatures, "minimum_database_version", (12,))
    assert DatabaseFeatures.minimum_database_version == (12,)

    vastbase._patch_minimum_database_version()

    assert DatabaseFeatures.minimum_database_version is None


# ============================================================
# 2. introspection SQL 改写
# ============================================================


def test_rewrite_removes_relispartition():
    """pg_class.relispartition 是 PG10+ 列，改写为 openGauss 的 parttype 谓词。"""
    sql = "SELECT CASE WHEN c.relispartition THEN 'p' ELSE 't' END FROM pg_class c"

    rewritten = vastbase.rewrite_introspection_sql(sql)

    assert "relispartition" not in rewritten
    assert "(c.parttype <> 'n')" in rewritten


def test_rewrite_replaces_conkey_ordinality():
    """conkey 是 1-based smallint[]，用 generate_subscripts 提供与下标一致的序号。"""
    sql = (
        "SELECT attname FROM unnest(c.conkey) WITH ORDINALITY cols(colid, arridx) "
        "JOIN pg_attribute AS ca ON cols.colid = ca.attnum ORDER BY cols.arridx"
    )

    rewritten = vastbase.rewrite_introspection_sql(sql)

    assert "WITH ORDINALITY" not in rewritten
    assert "generate_subscripts(c.conkey, 1) AS arridx" in rewritten
    # 改写后仍以 cols 为别名，外层的 cols.colid / cols.arridx 引用才不会断
    assert ") cols" in rewritten
    assert "cols.colid = ca.attnum" in rewritten


def test_rewrite_replaces_multi_arg_unnest_across_newlines():
    """多参数 unnest 跨行书写也要能匹配——Django 源码里它是折行的。"""
    sql = """
                FROM (
                    SELECT *
                    FROM
                        pg_index i,
                        unnest(i.indkey, i.indoption)
                            WITH ORDINALITY koi(key, option, arridx)
                ) idx
    """

    rewritten = vastbase.rewrite_introspection_sql(sql)

    assert "WITH ORDINALITY" not in rewritten
    assert "unnest(i.indkey, i.indoption)" not in rewritten
    assert "unnest(i.indkey) AS key" in rewritten
    assert "unnest(i.indoption) AS option" in rewritten
    assert "generate_subscripts(i.indkey, 1) AS arridx" in rewritten
    # 外层以 idx 为别名并引用 idx.* 的列，必须保留 i.* 展开
    assert "SELECT i.*," in rewritten


def test_rewrite_leaves_unrelated_sql_untouched():
    """非 introspection 语句不得被改动。"""
    sql = 'INSERT INTO "t" ("a") VALUES (%s)'

    assert vastbase.rewrite_introspection_sql(sql) == sql


def test_rewrite_is_idempotent():
    """重复改写结果稳定，避免代理 cursor 被层层包裹时出错。"""
    sql = "SELECT c.relispartition FROM pg_class c"

    once = vastbase.rewrite_introspection_sql(sql)
    twice = vastbase.rewrite_introspection_sql(once)

    assert once == twice


def test_get_table_list_sql_is_executable_on_vastbase(monkeypatch, introspection):
    """Django 真实的 get_table_list SQL 经补丁后不得再含 PG12+ 写法。"""
    monkeypatch.setattr(DatabaseIntrospection, "get_table_list", DatabaseIntrospection.get_table_list)
    vastbase._patch_introspection_pg12_syntax()
    cursor = _RecordingCursor()

    introspection.get_table_list(cursor)

    assert cursor.executed, "get_table_list 未执行任何 SQL，Django 实现可能已变"
    executed = "\n".join(cursor.executed)
    assert "relispartition" not in executed
    assert "(c.parttype <> 'n')" in executed


def test_get_constraints_sql_is_executable_on_vastbase(monkeypatch, introspection):
    """Django 真实的 get_constraints SQL 经补丁后不得再含 WITH ORDINALITY / 多参数 unnest。"""
    monkeypatch.setattr(DatabaseIntrospection, "get_constraints", DatabaseIntrospection.get_constraints)
    vastbase._patch_introspection_pg12_syntax()
    cursor = _RecordingCursor()

    introspection.get_constraints(cursor, "some_table")

    assert cursor.executed, "get_constraints 未执行任何 SQL，Django 实现可能已变"
    executed = "\n".join(cursor.executed)
    assert "WITH ORDINALITY" not in executed
    assert "unnest(i.indkey, i.indoption)" not in executed
    assert "generate_subscripts" in executed


# ============================================================
# 3. IDENTITY -> serial
# ============================================================


def test_auto_fields_fall_back_to_serial(monkeypatch):
    """Vastbase 不支持 GENERATED BY DEFAULT AS IDENTITY，AutoField 系列退回 serial。"""
    monkeypatch.setattr(DatabaseWrapper, "data_types", dict(DatabaseWrapper.data_types))
    monkeypatch.setattr(DatabaseWrapper, "data_types_suffix", dict(DatabaseWrapper.data_types_suffix))

    vastbase._patch_identity_to_serial()

    assert DatabaseWrapper.data_types["AutoField"] == "serial"
    assert DatabaseWrapper.data_types["BigAutoField"] == "bigserial"
    assert DatabaseWrapper.data_types["SmallAutoField"] == "smallserial"
    # serial 自带序列与默认值，不能再追加 IDENTITY 后缀
    assert DatabaseWrapper.data_types_suffix == {}
    # 其余字段类型不受影响
    assert DatabaseWrapper.data_types["BooleanField"] == "boolean"


# ============================================================
# 4. ON CONFLICT -> ON DUPLICATE KEY UPDATE
# ============================================================


def test_ignore_conflicts_uses_on_duplicate_key_update(monkeypatch):
    """无 target 的 ON CONFLICT DO NOTHING 在 B 模式不可用，改写为自赋值形式。"""
    monkeypatch.setattr(
        DatabaseOperations,
        "on_conflict_suffix_sql",
        DatabaseOperations.on_conflict_suffix_sql,
    )
    vastbase._patch_on_conflict_ignore()
    ops = DatabaseOperations(SimpleNamespace())
    fields = [SimpleNamespace(column="name"), SimpleNamespace(column="code")]

    suffix = ops.on_conflict_suffix_sql(fields, OnConflict.IGNORE, None, None)

    assert suffix == 'ON DUPLICATE KEY UPDATE "name" = "name"'
    assert "ON CONFLICT" not in suffix


def test_update_conflicts_keeps_native_on_conflict(monkeypatch):
    """UPDATE 分支的 ON CONFLICT(...) DO UPDATE 在 B 模式原生可用，保持 Django 实现。"""
    monkeypatch.setattr(
        DatabaseOperations,
        "on_conflict_suffix_sql",
        DatabaseOperations.on_conflict_suffix_sql,
    )
    vastbase._patch_on_conflict_ignore()
    ops = DatabaseOperations(SimpleNamespace())
    fields = [SimpleNamespace(column="name")]

    suffix = ops.on_conflict_suffix_sql(fields, OnConflict.UPDATE, ["value"], ["name"])

    assert suffix.startswith("ON CONFLICT")
    assert "EXCLUDED" in suffix
    assert "ON DUPLICATE KEY" not in suffix


def test_ignore_conflicts_without_fields_falls_back(monkeypatch):
    """fields 为空时无列可自赋值，退回原实现而不是生成非法 SQL。"""
    monkeypatch.setattr(
        DatabaseOperations,
        "on_conflict_suffix_sql",
        DatabaseOperations.on_conflict_suffix_sql,
    )
    vastbase._patch_on_conflict_ignore()
    ops = DatabaseOperations(SimpleNamespace())

    suffix = ops.on_conflict_suffix_sql([], OnConflict.IGNORE, None, None)

    assert suffix == "ON CONFLICT DO NOTHING"


# ============================================================
# 5. 序列重置
# ============================================================


def test_sequence_reset_sql_is_noop(monkeypatch):
    """B 模式下 serial 落地为 auto_increment，其序列拒绝 setval，重置须成为 no-op。"""
    monkeypatch.setattr(DatabaseOperations, "sequence_reset_sql", DatabaseOperations.sequence_reset_sql)
    monkeypatch.setattr(
        DatabaseOperations,
        "sequence_reset_by_name_sql",
        DatabaseOperations.sequence_reset_by_name_sql,
    )
    vastbase._patch_sequence_reset_sql()
    ops = DatabaseOperations(SimpleNamespace())

    assert ops.sequence_reset_sql(None, [object()]) == []
    assert ops.sequence_reset_by_name_sql(None, [{"table": "t", "column": "id"}]) == []


# ============================================================
# 6. naive datetime -> UTC aware
# ============================================================


def test_naive_datetime_is_converted_to_utc():
    """服务端不带时区偏移，会话时区固定 UTC，故裸值补 UTC 即正确时刻。"""
    naive = datetime.datetime(2026, 9, 7, 3, 0, 0)

    converted = vastbase._convert_naive_datetime(naive, None, None)

    assert converted.tzinfo == datetime.timezone.utc
    assert converted.timestamp() == naive.replace(tzinfo=datetime.timezone.utc).timestamp()


def test_aware_datetime_is_left_untouched():
    """已带时区的值不得被二次改写。"""
    aware = datetime.datetime(2026, 9, 7, 11, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))

    assert vastbase._convert_naive_datetime(aware, None, None) is aware


def test_none_datetime_is_left_untouched():
    assert vastbase._convert_naive_datetime(None, None, None) is None


def test_converter_registered_only_for_datetime_fields(monkeypatch, settings):
    """只给 DateTimeField 挂转换器，其它字段类型不受影响。"""
    settings.USE_TZ = True
    monkeypatch.setattr(DatabaseOperations, "get_db_converters", DatabaseOperations.get_db_converters)
    vastbase._patch_naive_datetime_converter()
    ops = DatabaseOperations(SimpleNamespace())

    dt_expr = SimpleNamespace(output_field=SimpleNamespace(get_internal_type=lambda: "DateTimeField"))
    char_expr = SimpleNamespace(output_field=SimpleNamespace(get_internal_type=lambda: "CharField"))

    assert vastbase._convert_naive_datetime in ops.get_db_converters(dt_expr)
    assert vastbase._convert_naive_datetime not in ops.get_db_converters(char_expr)


def test_converter_not_registered_when_use_tz_disabled(monkeypatch, settings):
    """USE_TZ=False 时 Django 本就使用 naive datetime，不应改写。"""
    settings.USE_TZ = False
    monkeypatch.setattr(DatabaseOperations, "get_db_converters", DatabaseOperations.get_db_converters)
    vastbase._patch_naive_datetime_converter()
    ops = DatabaseOperations(SimpleNamespace())

    dt_expr = SimpleNamespace(output_field=SimpleNamespace(get_internal_type=lambda: "DateTimeField"))

    assert vastbase._convert_naive_datetime not in ops.get_db_converters(dt_expr)


# ============================================================
# 7. psycopg3 timestamptz 解析
# ============================================================


def test_session_offset_is_detected_and_formatted(monkeypatch):
    """会话偏移由实测得出，而非硬编码 UTC。"""
    monkeypatch.setattr(vastbase, "_SESSION_UTC_OFFSET", b"+00:00")
    monkeypatch.setattr(vastbase, "_SESSION_OFFSET_LOGGED", False)

    # 东八区：28800 秒
    connection = _FakeConnection(28800)
    vastbase._capture_session_utc_offset(None, connection)

    assert vastbase._SESSION_UTC_OFFSET == b"+08:00"


def test_session_offset_handles_utc_and_negative(monkeypatch):
    """UTC 与西时区都要格式化正确。"""
    monkeypatch.setattr(vastbase, "_SESSION_UTC_OFFSET", b"+99:99")
    monkeypatch.setattr(vastbase, "_SESSION_OFFSET_LOGGED", True)

    vastbase._capture_session_utc_offset(None, _FakeConnection(0))
    assert vastbase._SESSION_UTC_OFFSET == b"+00:00"

    # 西五区半：-19800 秒
    vastbase._capture_session_utc_offset(None, _FakeConnection(-19800))
    assert vastbase._SESSION_UTC_OFFSET == b"-05:30"


def test_session_offset_falls_back_when_query_fails(monkeypatch):
    """探测失败不得阻断建连，沿用既有偏移。"""
    monkeypatch.setattr(vastbase, "_SESSION_UTC_OFFSET", b"+00:00")
    monkeypatch.setattr(vastbase, "_SESSION_OFFSET_LOGGED", True)

    vastbase._capture_session_utc_offset(None, _FakeConnection(0, fail=True))

    assert vastbase._SESSION_UTC_OFFSET == b"+00:00"


def test_non_postgresql_connection_is_ignored(monkeypatch):
    """其它 vendor 的连接不参与偏移探测。"""
    monkeypatch.setattr(vastbase, "_SESSION_UTC_OFFSET", b"+03:00")

    connection = _FakeConnection(28800)
    connection.vendor = "sqlite"
    vastbase._capture_session_utc_offset(None, connection)

    assert vastbase._SESSION_UTC_OFFSET == b"+03:00"


# ============================================================
# 幂等
# ============================================================


def test_apply_early_patches_is_idempotent(monkeypatch):
    """重复调用只生效一次，避免代理 cursor / 后缀 SQL 被反复包裹。"""
    monkeypatch.setattr(vastbase, "_patches_applied", False)
    calls = []
    monkeypatch.setattr(vastbase, "_patch_minimum_database_version", lambda: calls.append("version"))
    monkeypatch.setattr(vastbase, "_patch_introspection_pg12_syntax", lambda: calls.append("intro"))
    monkeypatch.setattr(vastbase, "_patch_identity_to_serial", lambda: calls.append("serial"))
    monkeypatch.setattr(vastbase, "_patch_on_conflict_ignore", lambda: calls.append("conflict"))
    monkeypatch.setattr(vastbase, "_patch_sequence_reset_sql", lambda: calls.append("sequence"))
    monkeypatch.setattr(vastbase, "_patch_naive_datetime_converter", lambda: calls.append("datetime"))
    monkeypatch.setattr(vastbase, "_patch_psycopg3_timestamptz_missing_tz", lambda: calls.append("loader"))

    vastbase.apply_early_patches()
    vastbase.apply_early_patches()

    assert calls == [
        "version",
        "intro",
        "serial",
        "conflict",
        "sequence",
        "datetime",
        "loader",
    ]
