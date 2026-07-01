class NoStorageMetricsError(RuntimeError):
    """Raised when a storage monitor run produced no usable metrics."""


def _has_metric_points(metric_payload):
    if isinstance(metric_payload, dict):
        return any(_has_metric_points(value) for value in metric_payload.values())
    if isinstance(metric_payload, (list, tuple)):
        return len(metric_payload) > 0
    return metric_payload is not None


def ensure_storage_metrics(data):
    if not isinstance(data, dict) or not data:
        raise NoStorageMetricsError("storage monitor produced no metrics")

    for metrics in data.values():
        if isinstance(metrics, dict) and any(
            _has_metric_points(value) for value in metrics.values()
        ):
            return data

    raise NoStorageMetricsError("storage monitor produced no metrics")


def to_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def store_metric(data, resource_id, metric_name, value, dims=()):
    value = to_float(value)
    if value is None:
        return
    data.setdefault(resource_id, {}).setdefault(metric_name, {}).setdefault(
        dims, []
    ).append((None, value))


def store_metric_group(data, resource_id, item, field_map, dims=(), divisor=1.0):
    for metric_name, field_name in field_map.items():
        value = to_float(item.get(field_name))
        if value is None:
            continue
        if divisor != 1.0:
            value = round(value / divisor, 3)
        store_metric(data, resource_id, metric_name, value, dims=dims)
