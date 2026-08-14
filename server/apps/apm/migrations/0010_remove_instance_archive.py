from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("apm", "0009_service_language_remove_builtin_application")]

    operations = [
        migrations.RemoveField(model_name="apmserviceinstance", name="archive_reason"),
        migrations.RemoveField(model_name="apmserviceinstance", name="archived_at"),
    ]
