from collections.abc import Callable

from django.db import models, transaction
from django.db.models.expressions import BaseExpression


class ConditionalUniqueGuardQuerySet(models.QuerySet):
    """让条件唯一 guard 覆盖 Django 的标准批量写入口。"""

    guard_rules: dict[str, tuple[str, Callable[[object], bool | None]]] = {}

    def update(self, **kwargs):
        for source_field, (guard_field, predicate) in self.guard_rules.items():
            if guard_field in kwargs and source_field not in kwargs:
                raise ValueError(f"{guard_field} 是派生保护字段，不能单独更新")
            if source_field not in kwargs:
                continue
            value = kwargs[source_field]
            if isinstance(value, BaseExpression):
                raise ValueError(f"{source_field} 表达式更新无法安全推导 {guard_field}，请使用 bulk_update 或逐条 save")
            kwargs[guard_field] = predicate(value)
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            self._sync_guards(obj)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        objs = list(objs)
        fields = list(fields)
        guarded_sources = set()
        for source_field, (guard_field, _) in self.guard_rules.items():
            if guard_field in fields and source_field not in fields:
                raise ValueError(f"{guard_field} 是派生保护字段，不能单独更新")
            if source_field in fields and guard_field not in fields:
                fields.append(guard_field)
            if source_field in fields:
                guarded_sources.add(source_field)
        for obj in objs:
            self._sync_guards(obj)
        if guarded_sources:
            with transaction.atomic(using=self.db):
                for obj in objs:
                    obj.save(update_fields=fields, using=self.db)
            return len(objs)
        return super().bulk_update(objs, fields, *args, **kwargs)

    def _sync_guards(self, obj):
        for source_field, (guard_field, predicate) in self.guard_rules.items():
            setattr(obj, guard_field, predicate(getattr(obj, source_field)))
