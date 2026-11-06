"""显式名单的路由字段迁移，默认只读；不改任务、参数与调度。"""

import json
import os
from pathlib import Path

from django.db import transaction
from django_celery_beat.models import PeriodicTask, PeriodicTasks

from apps.core.celery_runtime.manifest import TASK_ROUTES

FIELDS = ("queue", "exchange", "routing_key")


def route_fields(row):
    return {field: getattr(row, field) for field in FIELDS}


def save_snapshot(path, changes):
    if path is None:
        raise ValueError("应用路由变更必须指定新的快照文件")
    # 独占创建，避免覆盖原始恢复点；字段中不包含任务参数。
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
        json.dump({"version": 1, "changes": changes}, output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())


def _selected(ids):
    if not ids or len(ids) > 1000 or len(set(ids)) != len(ids) or any(type(pk) is not int or pk < 1 for pk in ids):
        raise ValueError("必须提供 1–1000 个不重复的正整数周期任务 ID")
    rows = list(PeriodicTask.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(rows) != len(ids):
        raise ValueError("部分周期任务不存在")
    return rows


@transaction.atomic
def migrate_routes(ids, registered, snapshot=None, apply=False):
    changes = []
    for row in _selected(ids):
        if row.task not in TASK_ROUTES or row.task not in registered:
            raise ValueError(f"周期任务 {row.pk} 未确认注册或未分类，不能自动修复")
        changes.append(
            {
                "id": row.pk,
                "task": row.task,
                "before": route_fields(row),
                "after": {"queue": TASK_ROUTES[row.task], "exchange": None, "routing_key": None},
            }
        )
    if apply:
        save_snapshot(snapshot, changes)
        for change in changes:
            PeriodicTask.objects.filter(pk=change["id"]).update(**change["after"])
        PeriodicTasks.update_changed()
    return changes


@transaction.atomic
def restore_routes(snapshot, apply=False):
    data = json.loads(Path(snapshot).read_text())
    if data.get("version") != 1 or not isinstance(data.get("changes"), list):
        raise ValueError("路由快照格式错误")
    changes = data["changes"]
    rows = {row.pk: row for row in _selected([change["id"] for change in changes])}
    for change in changes:
        for side in ("before", "after"):
            fields = change[side]
            if set(fields) != set(FIELDS) or any(value is not None and (not isinstance(value, str) or len(value) > 200) for value in fields.values()):
                raise ValueError("快照仅允许三个路由字段")
        row = rows[change["id"]]
        if row.task != change["task"] or route_fields(row) != change["after"]:
            raise ValueError(f"周期任务 {row.pk} 已发生变化，恢复冲突")
    if apply:
        for change in changes:
            PeriodicTask.objects.filter(pk=change["id"]).update(**change["before"])
        PeriodicTasks.update_changed()
    return changes
