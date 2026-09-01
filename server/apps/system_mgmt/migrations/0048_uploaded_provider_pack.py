from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0047_group_is_delete"),
    ]

    operations = [
        migrations.CreateModel(
            name="UploadedProviderPack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("key", models.CharField(db_index=True, max_length=64, unique=True)),
                ("pack_revision", models.PositiveIntegerField()),
                ("archive", models.BinaryField()),
                ("author_version", models.CharField(blank=True, default="", max_length=64)),
                ("name", models.CharField(blank=True, default="", max_length=128)),
            ],
            options={
                "db_table": "system_mgmt_uploadedproviderpack",
                "ordering": ("key",),
            },
        ),
    ]
