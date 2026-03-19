# Generated manually - Add indexes to UserRule for query performance

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0026_alter_channel_channel_type"),
    ]

    operations = [
        # Add composite index on (username, domain) for the most common query pattern
        migrations.AddIndex(
            model_name="userrule",
            index=models.Index(fields=["username", "domain"], name="system_mgmt_userrule_user_dom"),
        ),
        # Add index on username alone for queries that only filter by username
        migrations.AddIndex(
            model_name="userrule",
            index=models.Index(fields=["username"], name="system_mgmt_userrule_username"),
        ),
    ]
