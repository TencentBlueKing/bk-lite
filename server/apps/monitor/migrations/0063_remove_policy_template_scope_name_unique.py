from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0062_userhabit_and_remove_viewcolumnpreference"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="policytemplate",
            name="uniq_policy_template_scope_name",
        ),
    ]
