from django.db import migrations, models


def backfill_scenarios(apps, schema_editor):
    """根据现有记录的 type / model_object 回填场景，保证旧数据语义正确"""
    ChangeRecord = apps.get_model("cmdb", "ChangeRecord")
    # 关联类操作
    ChangeRecord.objects.filter(type__in=["create_edge", "delete_edge"]).update(
        scenario="relation_change"
    )
    # 模型管理 - 通过 model_object 字段识别（"模型管理"）
    ChangeRecord.objects.filter(model_object="模型管理").update(
        scenario="model_management_change"
    )
    # 其余记录走 default = ordinary_attribute_change，无需手动写


class Migration(migrations.Migration):

    dependencies = [
        ("cmdb", "0019_alter_collectmodels_exec_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="changerecord",
            name="scenario",
            field=models.CharField(
                choices=[
                    ("device_lifecycle", "设备流转"),
                    ("relation_change", "关系变更"),
                    ("ordinary_attribute_change", "普通属性变更"),
                    ("collect_automation_change", "自动采集"),
                    ("model_management_change", "模型管理变更"),
                ],
                db_index=True,
                default="ordinary_attribute_change",
                max_length=40,
                verbose_name="变更场景",
            ),
        ),
        migrations.RunPython(backfill_scenarios, migrations.RunPython.noop),
    ]
