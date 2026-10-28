from django.db import migrations, models

METRIC_CHOICES = [
    ("error_rate", "错误率"),
    ("error_count", "错误数"),
    ("p50", "P50"),
    ("p75", "P75"),
    ("p90", "P90"),
    ("p95", "P95"),
    ("p99", "P99"),
    ("latency_avg", "平均时延"),
    ("latency_max", "最大时延"),
    ("slow_request_count", "慢请求数"),
    ("slow_request_rate", "慢请求占比"),
    ("apdex", "Apdex"),
    ("throughput", "吞吐"),
    ("no_traffic", "无流量"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0021_apmpolicy_compare_offset_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="slow_threshold_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="apdex_threshold_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="apmpolicy",
            name="metric_type",
            field=models.CharField(choices=METRIC_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name="apmalert",
            name="metric_type",
            field=models.CharField(choices=METRIC_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name="apmevent",
            name="item",
            field=models.CharField(choices=METRIC_CHOICES, db_index=True, max_length=32),
        ),
    ]
