"""信创库 DDL 常自动提交，迁移中途失败后对象可能已消失。

把「对象不存在」当成删除成功，其它错误继续抛出。
"""

from django.db import migrations

MISSING_OBJECT_CODES = {
    -2106,  # Dameng: invalid / missing table
    -2139,  # Dameng: index not exists
    1051,  # MySQL: unknown table
    1091,  # MySQL: can't DROP; check that column/key exists
    1146,  # MySQL: table doesn't exist
}

DUPLICATE_INDEX_CODES = {
    -3236,  # Dameng: such column list already indexed
}

MISSING_OBJECT_HINTS = (
    "not exists",
    "does not exist",
    "unknown table",
    "unknown index",
    "check that it exists",
    "check that column/key exists",
    "不存在",
    "无效的表",
)

DUPLICATE_INDEX_HINTS = (
    "already indexed",
    "duplicate key name",
    "duplicate index",
    "此列列表已索引",
)


def _exception_has_code_or_hint(exc: BaseException, codes: set[int], hints: tuple[str, ...]) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        text = str(current).lower()
        if any(hint.lower() in text for hint in hints):
            return True
        for arg in getattr(current, "args", ()):
            if isinstance(arg, int) and arg in codes:
                return True
            code = getattr(arg, "code", None)
            if code is None:
                continue
            try:
                if int(code) in codes:
                    return True
            except (TypeError, ValueError):
                continue
        current = current.__cause__ or current.__context__
    return False


def missing_object_error(exc: BaseException) -> bool:
    return _exception_has_code_or_hint(exc, MISSING_OBJECT_CODES, MISSING_OBJECT_HINTS)


def already_indexed_error(exc: BaseException) -> bool:
    return _exception_has_code_or_hint(exc, DUPLICATE_INDEX_CODES, DUPLICATE_INDEX_HINTS)


def run_ignoring_missing_object(operation):
    try:
        return operation()
    except Exception as exc:
        if missing_object_error(exc):
            return None
        raise


def install_idempotent_schema_editor():
    """达梦 CreateModel 会把 unique/db_index/Index 编成多条 CREATE INDEX，后一条常 -3236。"""
    from django.db import connection, transaction
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

    # 达梦 DDL 自动提交。Django 在 atomic 迁移里禁止 DDL，RunPython.create_model 会直接失败。
    connection.features.can_rollback_ddl = True

    original = BaseDatabaseSchemaEditor.execute
    if getattr(original, "_compat_idempotent_ddl", False):
        return original

    def execute(self, sql, params=None):
        try:
            return original(self, sql, params)
        except transaction.TransactionManagementError:
            self.connection.features.can_rollback_ddl = True
            return original(self, sql, params)
        except Exception as exc:
            text = str(sql or "").upper()
            if already_indexed_error(exc) and "INDEX" in text:
                return None
            if missing_object_error(exc) and any(token in text for token in ("DROP INDEX", "DROP TABLE", "DROP CONSTRAINT")):
                return None
            raise

    execute._compat_idempotent_ddl = True
    BaseDatabaseSchemaEditor.execute = execute
    return execute


class FakeRemoveIndex(migrations.RemoveIndex):
    """对应 FakeAddIndex：这个名字从未在目标库创建。"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class RemoveIndexIfExists(migrations.RemoveIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        try:
            super().database_forwards(app_label, schema_editor, from_state, to_state)
        except Exception as exc:
            if missing_object_error(exc):
                return
            raise


class RemoveFieldIfExists(migrations.RemoveField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        try:
            super().database_forwards(app_label, schema_editor, from_state, to_state)
        except Exception as exc:
            if missing_object_error(exc):
                return
            raise


class AlterUniqueTogetherIfExists(migrations.AlterUniqueTogether):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        try:
            super().database_forwards(app_label, schema_editor, from_state, to_state)
        except Exception as exc:
            if missing_object_error(exc):
                return
            raise
