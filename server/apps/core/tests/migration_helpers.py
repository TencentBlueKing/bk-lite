from contextlib import contextmanager

from django.db.migrations.executor import MigrationExecutor


def migrate_to(connection, target):
    """迁移到目标状态，并返回与该 schema 对应的历史 app registry。"""
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@contextmanager
def migrated_from(connection, old_target, restore_target):
    """把测试库迁到历史状态，并保证离开场景时恢复到当前状态。"""
    try:
        yield migrate_to(connection, old_target)
    finally:
        migrate_to(connection, restore_target)
