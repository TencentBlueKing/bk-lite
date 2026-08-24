import django.db.models.deletion
from django.db import migrations, models


def backfill_target_team_memberships(apps, schema_editor):
    Target = apps.get_model("job_mgmt", "Target")
    TargetTeamMembership = apps.get_model("job_mgmt", "TargetTeamMembership")
    pending = []
    for target in Target.objects.only("id", "team").iterator(chunk_size=1000):
        team_ids = set()
        values = target.team if isinstance(target.team, (list, tuple, set)) else [target.team]
        for value in values:
            if isinstance(value, dict):
                value = value.get("id")
            try:
                team_ids.add(int(value))
            except (TypeError, ValueError):
                continue
        pending.extend(TargetTeamMembership(target_id=target.id, team_id=team_id) for team_id in team_ids)
        if len(pending) >= 1000:
            TargetTeamMembership.objects.bulk_create(pending, batch_size=1000, ignore_conflicts=True)
            pending.clear()
    if pending:
        TargetTeamMembership.objects.bulk_create(pending, batch_size=1000, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("job_mgmt", "0016_jobexecution_enforce_scheduled_team_boundary")]

    operations = [
        migrations.CreateModel(
            name="TargetTeamMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("team_id", models.BigIntegerField()),
                (
                    "target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_memberships",
                        to="job_mgmt.target",
                    ),
                ),
            ],
            options={
                "db_table": "job_target_team_membership",
                "constraints": [models.UniqueConstraint(fields=("target", "team_id"), name="uniq_job_target_team")],
                "indexes": [models.Index(fields=["team_id", "target"], name="job_target_team_idx")],
            },
        ),
        migrations.RunPython(backfill_target_team_memberships, migrations.RunPython.noop),
    ]
