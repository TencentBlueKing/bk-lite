from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.comparison
import django.db.models.functions.text


class Migration(migrations.Migration):
    dependencies = [("monitor", "0050_monitor_instance_summary_facts")]

    operations = [
        migrations.DeleteModel(name="PolicyTemplate"),
        migrations.CreateModel(
            name="PolicyTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("key", models.CharField(max_length=255, verbose_name="模板稳定标识")),
                ("scope_key", models.CharField(db_index=True, max_length=64, verbose_name="模板唯一性作用域")),
                ("template_type", models.CharField(choices=[("builtin", "内置"), ("custom", "自定义")], db_index=True, max_length=20, verbose_name="模板类型")),
                ("organization", models.IntegerField(blank=True, db_index=True, null=True, verbose_name="所属项目")),
                ("name", models.CharField(max_length=100, verbose_name="模板名称")),
                ("description", models.TextField(blank=True, default="", verbose_name="模板描述")),
                ("config", models.JSONField(default=dict, verbose_name="策略模板配置")),
                ("monitor_object", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="monitor.monitorobject", verbose_name="监控对象")),
                ("plugin", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="monitor.monitorplugin", verbose_name="监控插件")),
            ],
            options={
                "verbose_name": "监控策略模板",
                "verbose_name_plural": "监控策略模板",
            },
        ),
        migrations.AddConstraint(
            model_name="policytemplate",
            constraint=models.UniqueConstraint(fields=("scope_key", "key"), name="uniq_policy_template_scope_key"),
        ),
        migrations.AddConstraint(
            model_name="policytemplate",
            constraint=models.UniqueConstraint(fields=("scope_key", "monitor_object", "plugin", "name"), name="uniq_policy_template_scope_name"),
        ),
        migrations.AddConstraint(
            model_name="policytemplate",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("organization__isnull", True),
                        ("scope_key", "builtin"),
                        ("template_type", "builtin"),
                    ),
                    models.Q(
                        ("organization__isnull", False),
                        (
                            "scope_key",
                            django.db.models.functions.text.Concat(
                                models.Value("custom:"),
                                django.db.models.functions.comparison.Cast(
                                    models.F("organization"),
                                    output_field=models.CharField(),
                                ),
                            ),
                        ),
                        ("template_type", "custom"),
                    ),
                    _connector="OR",
                ),
                name="policy_template_type_org_consistent",
            ),
        ),
    ]
