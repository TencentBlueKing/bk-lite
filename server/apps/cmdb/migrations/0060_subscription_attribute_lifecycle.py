from django.db import migrations

LIFECYCLE_ADDED = "instance_added"
LIFECYCLE_UPDATED = "attribute_change"
LIFECYCLE_DELETED = "instance_deleted"


def expand_trigger_types(trigger_types):
    """旧的「属性变化」同时覆盖新增、修改、删除，迁移时补齐缺失类型。"""
    types = list(trigger_types or [])
    if LIFECYCLE_UPDATED not in types:
        return types
    for extra in (LIFECYCLE_ADDED, LIFECYCLE_DELETED):
        if extra not in types:
            types.append(extra)
    return types


def expand_legacy_attribute_lifecycle(apps, schema_editor):
    subscription_rule = apps.get_model("cmdb", "SubscriptionRule")
    for rule in subscription_rule.objects.all().iterator():
        expanded = expand_trigger_types(rule.trigger_types)
        if expanded != list(rule.trigger_types or []):
            rule.trigger_types = expanded
            rule.save(update_fields=["trigger_types"])


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0059_alter_collectmodels_task_type"),
    ]

    operations = [
        migrations.RunPython(expand_legacy_attribute_lifecycle, migrations.RunPython.noop),
    ]
