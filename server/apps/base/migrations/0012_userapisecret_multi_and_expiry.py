from django.db import migrations, models

from apps.core.openapi.token_scope import migrate_stored_scope


def backfill_user_api_secret_names(apps, schema_editor):
    UserAPISecret = apps.get_model("base", "UserAPISecret")
    for row in UserAPISecret.objects.all().iterator():
        name = (row.name or "").strip()
        if not name:
            row.name = f"token-{row.id}"
            row.save(update_fields=["name"])

    taken = set()
    for row in UserAPISecret.objects.all().order_by("id").iterator():
        key = (row.username, row.domain, row.team, row.name)
        if key in taken:
            suffix = 0
            while key in taken:
                suffix += 1
                candidate = f"{row.name}-{row.id}" if suffix == 1 else f"{row.name}-{row.id}-{suffix}"
                key = (row.username, row.domain, row.team, candidate)
            row.name = key[3]
            row.save(update_fields=["name"])
        taken.add(key)


def migrate_user_api_secret_scopes(apps, schema_editor):
    UserAPISecret = apps.get_model("base", "UserAPISecret")
    for row in UserAPISecret.objects.all().iterator():
        next_scope = migrate_stored_scope(row.scope)
        if row.scope != next_scope:
            row.scope = next_scope
            row.save(update_fields=["scope"])


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0011_alter_userapisecret_api_secret"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="userapisecret",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="userapisecret",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userapisecret",
            name="name",
            field=models.CharField(default="", max_length=128),
        ),
        migrations.AddField(
            model_name="userapisecret",
            name="scope",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_user_api_secret_names, migrations.RunPython.noop),
        migrations.RunPython(migrate_user_api_secret_scopes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="userapisecret",
            constraint=models.UniqueConstraint(
                fields=("username", "domain", "team", "name"),
                name="uniq_userapisecret_username_domain_team_name",
            ),
        ),
    ]
