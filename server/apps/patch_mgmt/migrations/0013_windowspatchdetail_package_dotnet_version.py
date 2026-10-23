from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("patch_mgmt", "0012_patchsource_connectivity_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="windowspatchdetail",
            name="package_dotnet_version",
            field=models.CharField(blank=True, default="", max_length=8, verbose_name=".NET 包版本"),
        ),
    ]
