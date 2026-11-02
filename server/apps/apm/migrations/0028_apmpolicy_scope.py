from hashlib import sha256

import django.db.models.deletion
from django.db import migrations, models


def backfill_policy_scope(apps, schema_editor):
    policy_model = apps.get_model("apm", "ApmPolicy")
    state_model = apps.get_model("apm", "ApmPolicyTargetState")
    for policy in policy_model.objects.all().iterator():
        if policy.endpoints and policy.endpoint_mode == "service":
            policy.endpoint_mode = "selected"
            policy.save(update_fields=["endpoint_mode"])
    for state in state_model.objects.select_related("policy").iterator():
        service_id = state.service_id or state.policy.service_id
        instance_id = state.instance_id or ""
        state.service_id = service_id
        state.instance_id = instance_id
        state.target_key = sha256(
            f"service={service_id}\x00endpoint={state.endpoint or ''}\x00version={state.version or ''}\x00instance={instance_id}".encode()
        ).hexdigest()
        state.save(update_fields=["service", "instance_id", "target_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0027_apmpolicy_conditions"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="scope_mode",
            field=models.CharField(
                choices=[("service", "单服务"), ("services", "多服务"), ("application", "按应用")],
                default="service",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="service_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="policies",
                to="apm.apmapplication",
            ),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="endpoint_mode",
            field=models.CharField(
                choices=[("service", "服务整体"), ("selected", "手选端点"), ("all", "全部端点")],
                default="service",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="instance_mode",
            field=models.CharField(
                choices=[("all", "不按实例拆"), ("grouped", "按实例")],
                default="all",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="apmpolicytargetstate",
            name="service",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="policy_target_states",
                to="apm.apmservice",
            ),
        ),
        migrations.AddField(
            model_name="apmpolicytargetstate",
            name="instance_id",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
        migrations.AddField(
            model_name="apmpolicytargetstate",
            name="missed_rounds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="apmalert",
            name="instance_id",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
        migrations.RunPython(backfill_policy_scope, migrations.RunPython.noop),
    ]
