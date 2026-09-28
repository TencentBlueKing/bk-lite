from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0081_ensure_wiki_frozen_structure"),
    ]

    operations = [
        migrations.AddField(
            model_name="skillpackage",
            name="is_build_in",
            field=models.BooleanField(db_index=True, default=False, verbose_name="是否内置"),
        ),
    ]
