from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0036_operation_outbox_delivery")]

    operations = [
        migrations.CreateModel(
            name="CmdbUniqueWriteLock",
            fields=[
                ("lock_key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("owner_token", models.CharField(max_length=64)),
                ("lease_expires_at", models.DateTimeField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "cmdb_unique_write_lock"},
        ),
        migrations.AddIndex(
            model_name="cmdbuniquewritelock",
            index=models.Index(fields=["lease_expires_at"], name="cmdb_unique_lock_lease_idx"),
        ),
    ]
