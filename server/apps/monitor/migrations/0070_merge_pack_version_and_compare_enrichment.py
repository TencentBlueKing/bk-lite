# Merge the plugin pack-version branch with the policy compare-enrichment branch.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0069_monitorplugin_pack_version"),
        ("monitor", "0069_monitorpolicy_compare_enrichment"),
    ]

    operations = []
