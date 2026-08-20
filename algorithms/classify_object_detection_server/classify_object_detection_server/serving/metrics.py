"""Prometheus 指标定义."""

from bentoml import metrics

# 预测请求计数器
prediction_counter = metrics.Counter(
    name="predictions_total",
    documentation="Total number of predictions",
    labelnames=["model_source", "status"],
)

# 预测延迟直方图
prediction_duration = metrics.Histogram(
    name="prediction_duration_seconds",
    documentation="Prediction duration in seconds",
    labelnames=["model_source"],
)

# 模型加载计数器
model_load_counter = metrics.Counter(
    name="model_loads_total",
    documentation="Total number of model loads",
    labelnames=["source", "status"],
)

# 健康检查计数器
health_check_counter = metrics.Counter(
    name="health_checks_total",
    documentation="Total number of health checks",
)

image_budget_usage = metrics.Histogram(
    name="image_budget_usage",
    documentation="Observed image request resource usage",
    labelnames=["dimension"],
    buckets=(
        1024,
        4 * 1024,
        16 * 1024,
        64 * 1024,
        256 * 1024,
        1024 * 1024,
        4 * 1024 * 1024,
        16 * 1024 * 1024,
        64 * 1024 * 1024,
        256 * 1024 * 1024,
        1024 * 1024 * 1024,
        4 * 1024 * 1024 * 1024,
    ),
)
image_budget_exceeded_counter = metrics.Counter(
    name="image_budget_exceeded_total",
    documentation="Image request resource budget exceedances",
    labelnames=["dimension", "mode"],
)

image_decode_duration = metrics.Histogram(
    name="image_decode_duration_seconds",
    documentation="Image batch decode duration in seconds",
)
image_process_peak_rss = metrics.Histogram(
    name="image_process_peak_rss_bytes",
    documentation="Process peak resident set size observed during image requests",
    buckets=(
        64 * 1024 * 1024,
        128 * 1024 * 1024,
        256 * 1024 * 1024,
        512 * 1024 * 1024,
        1024 * 1024 * 1024,
        2 * 1024 * 1024 * 1024,
        4 * 1024 * 1024 * 1024,
        8 * 1024 * 1024 * 1024,
        16 * 1024 * 1024 * 1024,
    ),
)

# 检测目标计数器（目标检测特有）
detection_counter = metrics.Counter(
    name="detections_total",
    documentation="Total number of detected objects",
    labelnames=["model_source"],
)
