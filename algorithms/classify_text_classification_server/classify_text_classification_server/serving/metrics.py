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
