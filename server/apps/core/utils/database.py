from django.db import connections, transaction


def bulk_create_with_primary_keys(manager, objects, *, batch_size=None):
    """批量创建并保证返回对象都带主键。

    MySQL 5.7 不能从批量 INSERT 回填 AutoField。需要主键参与后续写入时，逐条
    插入比按非唯一业务字段回查更安全，避免并发批次相互串数据。
    """
    objects = list(objects)
    if not objects:
        return []
    if connections[manager.db].features.can_return_rows_from_bulk_insert:
        return manager.bulk_create(objects, batch_size=batch_size)
    with transaction.atomic(using=manager.db):
        for obj in objects:
            obj.save(force_insert=True, using=manager.db)
    return objects
