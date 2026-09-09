from django.db import migrations, models
import django.db.models.deletion


def backfill_policy_organizations(apps, schema_editor):
    PolicyOrganization = apps.get_model("apm", "ApmPolicyOrganization")
    ServiceOrganization = apps.get_model("apm", "ApmServiceOrganization")
    links = [
        PolicyOrganization(
            policy_id=policy_id,
            organization=organization,
            created_by="migration",
            updated_by="migration",
        )
        for policy_id, organization in (
            ServiceOrganization.objects.filter(service__policies__isnull=False)
            .values_list("service__policies", "organization")
            .distinct()
        )
        if policy_id is not None
    ]
    if links:
        PolicyOrganization.objects.bulk_create(links, ignore_conflicts=True)


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("apm", "0015_apm_deployment_event_lookup_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApmPolicyOrganization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                ("organization", models.BigIntegerField(db_index=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_links",
                        to="apm.apmpolicy",
                    ),
                ),
            ],
            options={
                "verbose_name": "APM 策略组织",
                "verbose_name_plural": "APM 策略组织",
            },
        ),
        migrations.AddConstraint(
            model_name="apmpolicyorganization",
            constraint=models.UniqueConstraint(fields=("policy", "organization"), name="apm_policy_org_unique"),
        ),
        migrations.RunPython(backfill_policy_organizations, noop_reverse),
    ]
