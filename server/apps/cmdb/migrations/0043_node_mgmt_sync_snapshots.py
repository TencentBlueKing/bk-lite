import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0042_collectmodels_system_code_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodemgmtsyncrun",
            name="snapshot_schema_version",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="nodemgmtsyncrun",
            name="snapshot_status",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="nodemgmtsyncrun",
            name="expected_region_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="NodeMgmtSyncRegionSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("cloud_region_id", models.CharField(max_length=64)),
                ("child_execution_id", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(max_length=32)),
                ("reason_code", models.CharField(blank=True, default="", max_length=64)),
                ("capture_status", models.CharField(default="pending", max_length=32)),
                ("capture_token", models.CharField(blank=True, default="", max_length=64)),
                ("capture_deadline", models.DateTimeField(blank=True, null=True)),
                ("capture_attempt", models.PositiveIntegerField(default=0)),
                ("row_quota", models.PositiveIntegerField(default=0)),
                ("byte_quota", models.PositiveBigIntegerField(default=0)),
                ("summary_json", models.JSONField(default=dict)),
                ("detail_retained", models.BooleanField(default=True)),
                ("cleanup_status", models.CharField(default="retained", max_length=32)),
                ("byte_size", models.PositiveBigIntegerField(default=0)),
                ("truncated", models.BooleanField(default=False)),
                (
                    "region_state",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshot",
                        to="cmdb.nodemgmtsyncregionstate",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="region_snapshots",
                        to="cmdb.nodemgmtsyncrun",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="nodemgmtsyncregionsnapshot",
            constraint=models.UniqueConstraint(
                fields=("run", "cloud_region_id", "child_execution_id"),
                name="cmdb_node_sync_snapshot_execution_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncregionsnapshot",
            index=models.Index(fields=["run", "capture_status"], name="cmdb_sync_snap_run_status"),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncregionsnapshot",
            index=models.Index(fields=["cleanup_status", "updated_at"], name="cmdb_sync_snap_cleanup"),
        ),
        migrations.CreateModel(
            name="NodeMgmtSyncSnapshotRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("bucket", models.CharField(default="raw_data", max_length=32)),
                ("ordinal", models.PositiveIntegerField()),
                ("row_type", models.CharField(max_length=32)),
                ("row_key", models.CharField(max_length=64)),
                ("inst_name", models.CharField(blank=True, default="", max_length=512)),
                ("ip_addr", models.CharField(blank=True, default="", max_length=255)),
                ("cloud_name", models.CharField(blank=True, default="", max_length=255)),
                ("pid", models.CharField(blank=True, default="", max_length=64)),
                ("process_name", models.CharField(blank=True, default="", max_length=512)),
                ("payload_json", models.JSONField(default=dict)),
                ("byte_size", models.PositiveIntegerField(default=0)),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rows",
                        to="cmdb.nodemgmtsyncregionsnapshot",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="nodemgmtsyncsnapshotrow",
            constraint=models.UniqueConstraint(
                fields=("snapshot", "bucket", "ordinal"),
                name="cmdb_node_sync_row_ordinal_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="nodemgmtsyncsnapshotrow",
            constraint=models.UniqueConstraint(
                fields=("snapshot", "row_key"),
                name="cmdb_node_sync_row_key_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncsnapshotrow",
            index=models.Index(fields=["snapshot", "bucket", "ordinal"], name="cmdb_sync_row_page"),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncsnapshotrow",
            index=models.Index(fields=["snapshot", "row_type"], name="cmdb_sync_row_type"),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncsnapshotrow",
            index=models.Index(fields=["snapshot", "ip_addr"], name="cmdb_sync_row_ip"),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncsnapshotrow",
            index=models.Index(fields=["snapshot", "pid"], name="cmdb_sync_row_pid"),
        ),
        migrations.AddIndex(
            model_name="nodemgmtsyncsnapshotrow",
            index=models.Index(fields=["snapshot", "process_name"], name="cmdb_sync_row_process"),
        ),
    ]
