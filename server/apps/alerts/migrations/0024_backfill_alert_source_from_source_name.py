"""回填 Alert.source FK（从 source_name 反查 AlertSource）。

2026-07-17 source_id 过滤失效 bug 修复的 data migration:
新增 Alert.source FK（migration 0023）后，回填历史告警的 source FK。
Alert.source_name 是字符串（AlertSource.name），通过 name 反查 AlertSource 设上 source。

可重入：使用 .update(source=...) 而非 save()，避免触发 signal；按 id 范围分批
（每次 1000 条）防止大事务。
"""

from django.db import migrations


def backfill_alert_source(apps, schema_editor):
    Alert = apps.get_model("alerts", "Alert")
    AlertSource = apps.get_model("alerts", "AlertSource")

    # 预加载 name -> id 映射（避免循环查询）
    name_to_id = {s.name: s.id for s in AlertSource.objects.all() if s.name}

    # 分批回填，限制每次查询条数
    BATCH = 1000
    qs = Alert.objects.filter(source__isnull=True).exclude(source_name__isnull=True).exclude(source_name="")
    total = qs.count()
    if not total:
        return

    updated = 0
    skipped_no_match = 0
    while True:
        # 每次拿一个 batch（不能用 .iterator 配合 .update）
        batch_ids = list(
            qs.values_list("id", "source_name")[:BATCH]
        )
        if not batch_ids:
            break

        per_alert_updates = []
        for alert_id, source_name in batch_ids:
            source_id = name_to_id.get(source_name)
            if source_id is None:
                skipped_no_match += 1
                continue
            per_alert_updates.append((alert_id, source_id))

        # 逐条 update（Django ORM 没有"批量按 id 设不同值"的 API）
        for alert_id, source_id in per_alert_updates:
            Alert.objects.filter(id=alert_id).update(source_id=source_id)
            updated += 1

        if len(batch_ids) < BATCH:
            break


def reverse_noop(apps, schema_editor):
    """回滚时不清空 source——避免历史告警丢信息；如果真的需要回滚，跑 SQL 手动清。"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0023_alert_source"),
    ]

    operations = [
        migrations.RunPython(backfill_alert_source, reverse_noop),
    ]
