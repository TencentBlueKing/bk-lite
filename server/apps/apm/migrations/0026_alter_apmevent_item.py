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
        ("apm", "0025_remove_apmpolicy_guard_conditions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apmevent",
            name="item",
            field=models.CharField(choices=METRIC_CHOICES, max_length=32),
        ),
    ]
