from django.db import migrations, models


def backfill_alert_organizations(apps, schema_editor):
    MonitorAlert = apps.get_model("monitor", "MonitorAlert")
    PolicyOrganization = apps.get_model("monitor", "PolicyOrganization")
    MonitorPolicy = apps.get_model("monitor", "MonitorPolicy")

    org_map = {}
    for policy_id, organization in PolicyOrganization.objects.values_list("policy_id", "organization"):
        org_map.setdefault(policy_id, []).append(organization)

    for policy_id, organizations in MonitorPolicy.objects.values_list("id", "organizations"):
        if policy_id in org_map or not organizations:
            continue
        org_map[policy_id] = list(organizations)

    updates = []
    for alert in MonitorAlert.objects.iterator():
        organizations = list(org_map.get(alert.policy_id) or [])
        if not organizations:
            continue
        alert.organizations = organizations
        updates.append(alert)
        if len(updates) >= 500:
            MonitorAlert.objects.bulk_update(updates, ["organizations"])
            updates = []
    if updates:
        MonitorAlert.objects.bulk_update(updates, ["organizations"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0065_merge_lifecycle_action_and_k8s_tolerations"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitoralert",
            name="organizations",
            field=models.JSONField(default=list, verbose_name="告警生成时所属组织"),
        ),
        migrations.RunPython(backfill_alert_organizations, migrations.RunPython.noop),
    ]
