"""信创库迁移补丁共用操作。

达梦和 MySQL 系的 DDL 自动提交：迁移中途失败时，前面的删除已经生效，迁移却未登记。
*IfExists 先查库，对象已经不在就跳过，重跑可以从任意中断点做完。
"""

from django.db import migrations

from apps.core.logger import logger

DUPLICATE_INDEX_CODES = {
    -3236,  # Dameng: such column list already indexed
}

DUPLICATE_INDEX_HINTS = (
    "already indexed",
    "此列列表已索引",
)


def _is_duplicate_index_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if any(hint in text for hint in DUPLICATE_INDEX_HINTS):
            return True
        for arg in getattr(current, "args", ()):
            code = arg if isinstance(arg, int) else getattr(arg, "code", None)
            try:
                if code is not None and int(code) in DUPLICATE_INDEX_CODES:
                    return True
            except (TypeError, ValueError):
                continue
        current = current.__cause__ or current.__context__
    return False


def _created_index_name(sql) -> str:
    parts = str(sql).split()
    return parts[2].strip('"`') if len(parts) > 2 else "-"


def install_idempotent_schema_editor():
    """只在 apps.core.db_patches.dameng.patch() 里安装；其它引擎不要调用。"""
    from django.db import connection
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

    # 达梦不能回滚 DDL。保持 False 时 Django 会把 RunPython 包进事务并拒绝其中的 DDL，
    # cmdb.0061 在 RunPython 里建备份表会直接失败。
    type(connection.features).can_rollback_ddl = True

    original = BaseDatabaseSchemaEditor.execute
    if getattr(original, "_compat_idempotent_ddl", False):
        return original

    def execute(self, sql, params=()):
        try:
            return original(self, sql, params)
        except Exception as exc:
            # 达梦拒绝在完全相同的列组合上再建一条普通索引（典型是 FK 自带索引 + Meta.indexes），
            # 已有索引就能覆盖查询。唯一约束走 ADD CONSTRAINT，不会进这里。
            if str(sql or "").lstrip().upper().startswith("CREATE INDEX") and _is_duplicate_index_error(exc):
                logger.warning(
                    "event=dameng_duplicate_index_skipped index=%s failed_stage=migrate error_type=%s",
                    _created_index_name(sql),
                    type(exc).__name__,
                )
                return None
            raise

    execute._compat_idempotent_ddl = True
    BaseDatabaseSchemaEditor.execute = execute
    return execute


def _table_exists(schema_editor, model) -> bool:
    names = schema_editor.connection.introspection.table_names()
    return model._meta.db_table.lower() in {name.lower() for name in names}


def _column_exists(schema_editor, model, column: str) -> bool:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, model._meta.db_table)
    return column.lower() in {item.name.lower() for item in description}


def _constraint_names(schema_editor, model) -> set[str]:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
    return {name.lower() for name in constraints}


class FakeRemoveIndex(migrations.RemoveIndex):
    """对应 FakeAddIndex：这个名字从未在目标库创建。"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class RemoveIndexIfExists(migrations.RemoveIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if not _table_exists(schema_editor, model):
            return
        if self.name.lower() not in _constraint_names(schema_editor, model):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class RemoveFieldIfExists(migrations.RemoveField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        field = model._meta.get_field(self.name)
        if field.many_to_many:
            through = field.remote_field.through
            if through._meta.auto_created and not _table_exists(schema_editor, through):
                return
        elif not _table_exists(schema_editor, model) or not _column_exists(schema_editor, model, field.column):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class AlterUniqueTogetherIfExists(migrations.AlterUniqueTogether):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        new_model = to_state.apps.get_model(app_label, self.name)
        if not self.allow_migrate_model(schema_editor.connection.alias, new_model):
            return
        old_model = from_state.apps.get_model(app_label, self.name)
        if not _table_exists(schema_editor, old_model):
            return
        # 约束已被上次中断的运行删掉时，Django 会先抛 ValueError("Found wrong number (0) ...")，
        # 不会走到数据库报错，所以只把仍在库里的旧约束交给 schema editor。
        existing = [
            fields
            for fields in old_model._meta.unique_together
            if schema_editor._constraint_names(
                old_model,
                [old_model._meta.get_field(name).column for name in fields],
                unique=True,
                primary_key=False,
            )
        ]
        schema_editor.alter_unique_together(new_model, existing, new_model._meta.unique_together)


class DeleteModelIfExists(migrations.DeleteModel):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.name)
        if not _table_exists(schema_editor, model):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
