from django.db import migrations, models
import django.db.models.deletion


def backfill_alert_organizations(apps, schema_editor):
    Alert = apps.get_model("log", "Alert")
    PolicyOrganization = apps.get_model("log", "PolicyOrganization")

    org_map = {}
    for policy_id, organization in PolicyOrganization.objects.values_list("policy_id", "organization"):
        org_map.setdefault(policy_id, []).append(organization)

    updates = []
    for alert in Alert.objects.iterator():
        organizations = list(org_map.get(alert.policy_id) or [])
        if not organizations:
            continue
        alert.organizations = organizations
        updates.append(alert)
        if len(updates) >= 500:
            Alert.objects.bulk_update(updates, ["organizations"])
            updates = []
    if updates:
        Alert.objects.bulk_update(updates, ["organizations"])


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0025_k8s_daemonset_tolerations"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="organizations",
            field=models.JSONField(default=list, verbose_name="告警生成时所属组织"),
        ),
        migrations.AlterField(
            model_name="alert",
            name="policy",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="log.policy",
                verbose_name="关联策略",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="policy",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="log.policy",
                verbose_name="关联策略",
            ),
        ),
        migrations.AlterField(
            model_name="alertsnapshot",
            name="policy",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="log.policy",
                verbose_name="关联策略",
            ),
        ),
        migrations.RunPython(backfill_alert_organizations, migrations.RunPython.noop),
    ]
