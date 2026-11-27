from django.db import migrations, models
from django.db.models import Q


def mark_builtin_default_root(apps, schema_editor):
    Group = apps.get_model("system_mgmt", "Group")
    Group.objects.filter(name="Default", parent_id=0).update(is_builtin=True)


def unmark_builtin_default_root(apps, schema_editor):
    Group = apps.get_model("system_mgmt", "Group")
    Group.objects.filter(name="Default", parent_id=0, is_builtin=True).update(is_builtin=False)


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0060_userloginlog_login_method_used_otp"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="is_builtin",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_builtin_default_root, unmark_builtin_default_root),
        migrations.AddConstraint(
            model_name="group",
            constraint=models.UniqueConstraint(
                fields=("is_builtin",),
                condition=Q(is_builtin=True),
                name="uniq_group_one_builtin",
            ),
        ),
    ]
