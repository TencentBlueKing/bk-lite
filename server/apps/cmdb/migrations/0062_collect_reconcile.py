import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0061_showfield_created_by_model_unique"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectReconcile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=128)),
                ("model_id", models.CharField(db_index=True, max_length=64)),
                ("version", models.PositiveIntegerField(default=1)),
            ],
            options={"db_table": "cmdb_collect_reconcile"},
        ),
        migrations.CreateModel(
            name="CollectReconcileOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(max_length=64)),
                ("position", models.PositiveIntegerField()),
                (
                    "reconcile",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orders", to="cmdb.collectreconcile"),
                ),
                (
                    "task",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reconcile_orders", to="cmdb.collectmodels"),
                ),
            ],
            options={"db_table": "cmdb_collect_reconcile_order"},
        ),
        migrations.AddConstraint(
            model_name="collectreconcile",
            constraint=models.UniqueConstraint(fields=("name", "model_id"), name="uniq_cmdb_reconcile_name_model"),
        ),
        migrations.AddConstraint(
            model_name="collectreconcileorder",
            constraint=models.UniqueConstraint(fields=("reconcile", "scope", "task"), name="uniq_cmdb_reconcile_order_task"),
        ),
        migrations.AddConstraint(
            model_name="collectreconcileorder",
            constraint=models.UniqueConstraint(fields=("reconcile", "scope", "position"), name="uniq_cmdb_reconcile_order_pos"),
        ),
        migrations.AddConstraint(
            model_name="collectreconcileorder",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", "member")),
                fields=("task",),
                name="uniq_cmdb_reconcile_member_task",
            ),
        ),
        migrations.AddIndex(
            model_name="collectreconcileorder",
            index=models.Index(fields=["task", "scope"], name="idx_reconcile_order_task_scope"),
        ),
    ]
