from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0067_wiki_directory_generation_navigation"),
    ]

    operations = [
        migrations.AddField(
            model_name="wikiknowledgebase",
            name="directory_migration_state",
            field=models.CharField(
                db_index=True,
                default="legacy",
                help_text="legacy / backfilling / ready / enabled",
                max_length=20,
            ),
        ),
    ]
