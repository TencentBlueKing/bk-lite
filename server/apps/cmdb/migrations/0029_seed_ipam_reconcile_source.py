# -- coding: utf-8 --
"""预置 IPAM 默认对账来源（host.ip_addr / network.ip）。

取代原先的 ipam_init management 命令：模型字段/关联由 model_config.xlsx + model_init 负责，
此处仅补 IPAMReconcileSource 这张 Django 表的种子数据，随 `make migrate` 自动落地。
"""
from django.db import migrations


def seed(apps, schema_editor):
    from apps.cmdb.models.ipam_models import seed_reconcile_sources

    seed_reconcile_sources(apps.get_model("cmdb", "IPAMReconcileSource"))


def unseed(apps, schema_editor):
    from apps.cmdb.models.ipam_models import DEFAULT_RECONCILE_SOURCES

    model_cls = apps.get_model("cmdb", "IPAMReconcileSource")
    for model_id, ip_attr_id in DEFAULT_RECONCILE_SOURCES:
        model_cls.objects.filter(model_id=model_id, ip_attr_id=ip_attr_id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cmdb", "0028_alter_changerecord_scenario_ipamreconcilesource"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
