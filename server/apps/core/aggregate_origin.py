"""运行期探测聚合库里各产品第一次出现序列的时间。

未写入起点视为没有聚合数据。探测失败只记一条日志，不抛给周期任务。
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.db import IntegrityError, transaction

from apps.core.aggregate_promql import AggregatePromqlClient
from apps.core.logger import logger, safe_exception_info
from apps.core.models.aggregate_origin import AggregateMetricOrigin

LOOKBACK = "35d"
MIN_UNIX_SECONDS = 1_000_000_000
# 起点表示该产品的计数序列开始存在。APM 只认 apm_calls_total，RUM 只认 rum_views_total。
# 晚到的其他序列不能提前起点。
PRODUCT_METRICS = (
    ("apm", "apm_calls_total"),
    ("rum", "rum_views_total"),
)


def floor_minute(value: datetime) -> datetime:
    aware = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.replace(second=0, microsecond=0)


def recorded_origin(product: str) -> datetime | None:
    row = AggregateMetricOrigin.objects.filter(product=product).only("started_at").first()
    if row is None:
        return None
    return row.started_at


def record_earliest(product: str, started_at: datetime) -> datetime:
    started_at = floor_minute(started_at)
    with transaction.atomic():
        row = AggregateMetricOrigin.objects.select_for_update().filter(product=product).first()
        if row is not None:
            if started_at < row.started_at:
                row.started_at = started_at
                row.save(update_fields=["started_at", "updated_at"])
            return row.started_at
    try:
        with transaction.atomic():
            return AggregateMetricOrigin.objects.create(product=product, started_at=started_at).started_at
    except IntegrityError:
        with transaction.atomic():
            row = AggregateMetricOrigin.objects.select_for_update().get(product=product)
            if started_at < row.started_at:
                row.started_at = started_at
                row.save(update_fields=["started_at", "updated_at"])
            return row.started_at


def _scalar_timestamp(result: list[dict]) -> float | None:
    if not result:
        return None
    sample = result[0].get("value")
    if not isinstance(sample, (list, tuple)) or len(sample) < 2:
        return None
    try:
        value = float(sample[1])
    except (TypeError, ValueError):
        return None
    if value < MIN_UNIX_SECONDS:
        return None
    return value


def probe_aggregate_origins(client: AggregatePromqlClient | None = None, *, at: datetime | None = None) -> dict:
    reader = client or AggregatePromqlClient.from_env()
    if not reader.available:
        return {"status": "unconfigured", "recorded": []}
    pending = [item for item in PRODUCT_METRICS if recorded_origin(item[0]) is None]
    if not pending:
        return {"status": "ok", "recorded": []}
    moment = at or datetime.now(UTC)
    recorded: list[str] = []
    failures: list[str] = []
    first_error: Exception | None = None
    for product, selector in pending:
        expression = f"min(tfirst_over_time({selector}[{LOOKBACK}]))"
        try:
            result = reader.query_instant(expression, at=moment)
            timestamp = _scalar_timestamp(result)
            if timestamp is None:
                continue
            record_earliest(product, datetime.fromtimestamp(timestamp, tz=UTC))
            recorded.append(product)
        except Exception as exc:
            failures.append(product)
            if first_error is None:
                first_error = exc
    if first_error is not None:
        logger.warning(
            "event=aggregate_origin_probe_failed products=%s failed_stage=probe error_type=%s",
            ",".join(failures),
            type(first_error).__name__,
            exc_info=safe_exception_info(first_error),
        )
        return {"status": "degraded", "recorded": recorded}
    return {"status": "ok", "recorded": recorded}
