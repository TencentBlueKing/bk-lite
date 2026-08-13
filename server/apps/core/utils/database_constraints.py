from django.db import models, transaction


class ConstraintValidatedQuerySet(models.QuerySet):
    """在 MySQL 5.7 不执行 CHECK 时覆盖标准 ORM 批量写入口。"""

    protected_fields: frozenset[str] = frozenset()

    def update(self, **kwargs):
        protected = self.protected_fields.intersection(kwargs)
        if protected:
            fields = ", ".join(sorted(protected))
            raise ValueError(f"{fields} 受跨数据库约束保护，请使用逐条 save")
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            obj._validate_database_constraints()
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        objs = list(objs)
        fields = list(fields)
        if not self.protected_fields.intersection(fields):
            return super().bulk_update(objs, fields, *args, **kwargs)
        with transaction.atomic(using=self.db):
            for obj in objs:
                obj.save(update_fields=fields, using=self.db)
        return len(objs)
