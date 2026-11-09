import inspect
import logging
from datetime import UTC, datetime

import pytest

from apps.core.aggregate_origin import probe_aggregate_origins
from apps.core.aggregate_promql import AggregateMetricsUnavailable, AggregatePromqlClient
from apps.core.apps import CoreConfig
from apps.core.celery_runtime.manifest import TASK_ROUTES
from apps.core.config import CELERY_BEAT_SCHEDULE
from apps.core.logger import SafeLogException
from apps.core.models.aggregate_origin import AggregateMetricOrigin
from apps.core.tasks.aggregate_origin import probe_aggregate_metric_origins

pytestmark = pytest.mark.django_db

RAW = datetime(2026, 11, 10, 0, 16, 17, tzinfo=UTC)
MINUTE = datetime(2026, 11, 10, 0, 16, tzinfo=UTC)
PROBE_AT = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)


def _sentinel(kind: str) -> str:
    return "-".join(["AGG", kind, "SENTINEL"])


class _Scripted:
    def __init__(self, values):
        self.available = True
        self.values = values
        self.expressions = []

    def query_instant(self, expression, *, at):
        self.expressions.append((expression, at))
        value = self.values[expression]
        if isinstance(value, Exception):
            raise value
        return value


APM_EXPR = "min(tfirst_over_time(apm_calls_total[35d]))"
RUM_EXPR = "min(tfirst_over_time(rum_views_total[35d]))"


def _values(*, apm=None, rum=None):
    return {
        APM_EXPR: apm if apm is not None else [],
        RUM_EXPR: rum if rum is not None else [],
    }


def _sample(moment: datetime):
    return [{"value": [0, str(moment.timestamp())]}]


def test_probe_persists_the_earliest_minute_and_ignores_later_or_empty_results():
    client = _Scripted(_values(apm=_sample(RAW), rum=_sample(datetime(2026, 11, 10, 0, 20, 5, tzinfo=UTC))))

    first = probe_aggregate_origins(client, at=PROBE_AT)

    assert first == {"status": "ok", "recorded": ["apm", "rum"]}
    assert client.expressions == [
        (APM_EXPR, PROBE_AT),
        (RUM_EXPR, PROBE_AT),
    ]
    assert "apm_calls_total" in APM_EXPR
    assert "apm_.*" not in APM_EXPR
    assert "rum_views_total" in RUM_EXPR
    assert "rum_.*" not in RUM_EXPR
    assert "__name__" not in RUM_EXPR
    assert AggregateMetricOrigin.objects.get(product="apm").started_at == MINUTE
    assert AggregateMetricOrigin.objects.get(product="rum").started_at == datetime(2026, 11, 10, 0, 20, tzinfo=UTC)

    follow_up = _Scripted(_values(apm=_sample(datetime(2026, 11, 10, 0, 10, 59, tzinfo=UTC))))
    again = probe_aggregate_origins(follow_up, at=PROBE_AT)
    assert again == {"status": "ok", "recorded": []}
    assert follow_up.expressions == []
    assert AggregateMetricOrigin.objects.get(product="apm").started_at == MINUTE
    assert AggregateMetricOrigin.objects.get(product="rum").started_at == datetime(2026, 11, 10, 0, 20, tzinfo=UTC)


def test_recorded_product_is_not_queried_again():
    AggregateMetricOrigin.objects.create(product="apm", started_at=MINUTE)
    client = _Scripted(_values(apm=_sample(datetime(2026, 11, 10, 0, 1, tzinfo=UTC)), rum=_sample(RAW)))

    result = probe_aggregate_origins(client, at=PROBE_AT)

    assert result == {"status": "ok", "recorded": ["rum"]}
    assert client.expressions == [(RUM_EXPR, PROBE_AT)]
    assert "apm_calls_total" not in client.expressions[0][0]
    assert AggregateMetricOrigin.objects.get(product="apm").started_at == MINUTE


def test_probe_ignores_timestamps_before_the_unix_second_floor():
    client = _Scripted(_values(apm=[{"value": [0, "999999999"]}]))

    result = probe_aggregate_origins(client, at=PROBE_AT)

    assert result == {"status": "ok", "recorded": []}
    assert AggregateMetricOrigin.objects.count() == 0


def test_unconfigured_probe_does_not_log_or_read_the_monitor_host(monkeypatch, caplog):
    monkeypatch.delenv("AGG_VICTORIAMETRICS_QUERY_URL", raising=False)
    monkeypatch.setenv("VICTORIAMETRICS_HOST", "http://monitor.example:8428")
    caplog.set_level(logging.WARNING, logger="app")

    result = probe_aggregate_origins(at=PROBE_AT)

    assert result == {"status": "unconfigured", "recorded": []}
    assert not [record for record in caplog.records if str(record.msg).startswith("event=aggregate_origin")]
    assert AggregateMetricOrigin.objects.count() == 0


def test_probe_logs_one_failure_and_keeps_products_that_succeeded(caplog):
    secret = _sentinel("BODY")
    client = _Scripted(
        _values(
            apm=_sample(RAW),
            rum=RuntimeError(secret),
        )
    )
    caplog.set_level(logging.WARNING, logger="app")

    result = probe_aggregate_origins(client, at=PROBE_AT)

    assert result == {"status": "degraded", "recorded": ["apm"]}
    assert AggregateMetricOrigin.objects.get(product="apm").started_at == MINUTE
    assert not AggregateMetricOrigin.objects.filter(product="rum").exists()
    records = [record for record in caplog.records if record.levelno == logging.WARNING and str(record.msg).startswith("event=aggregate_origin")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=aggregate_origin_probe_failed products=%s failed_stage=probe error_type=%s"
    assert record.args == ("rum", "RuntimeError")
    assert record.getMessage() == "event=aggregate_origin_probe_failed products=rum failed_stage=probe error_type=RuntimeError"
    assert record.exc_info[0] is SafeLogException
    formatted = logging.Formatter().format(record)
    assert formatted.count("Traceback (most recent call last)") == 1
    assert secret not in record.getMessage()
    assert secret not in formatted
    assert secret not in caplog.text


def test_http_probe_failure_logs_one_traceback_without_credentials_or_body(monkeypatch, caplog):
    password = _sentinel("PASSWORD")
    body = ("not-json " + _sentinel("BODY")).encode()

    class _Response:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size=65536):
            yield body

        def close(self):
            return None

    class _Session:
        def __init__(self):
            self.auth = None

        def get(self, url, **kwargs):
            self.auth = kwargs.get("auth")
            return _Response()

        def close(self):
            return None

    session = _Session()
    monkeypatch.setenv("AGG_VICTORIAMETRICS_QUERY_URL", "http://aggregate.test")
    monkeypatch.setenv("AGG_VICTORIAMETRICS_USER", "agg-user")
    monkeypatch.setenv("AGG_VICTORIAMETRICS_PASSWORD", password)
    client = AggregatePromqlClient.from_env(session=session)
    caplog.set_level(logging.WARNING, logger="app")

    result = probe_aggregate_origins(client, at=PROBE_AT)

    assert result == {"status": "degraded", "recorded": []}
    assert session.auth == ("agg-user", password)
    assert AggregateMetricOrigin.objects.count() == 0
    records = [record for record in caplog.records if record.levelno == logging.WARNING and str(record.msg).startswith("event=aggregate_origin")]
    assert len(records) == 1
    record = records[0]
    assert record.args == ("apm,rum", "AggregateMetricsUnavailable")
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is not None
    formatted = logging.Formatter().format(record)
    assert formatted.count("Traceback (most recent call last)") == 1
    assert password not in formatted
    assert _sentinel("BODY") not in formatted
    assert password not in caplog.text
    assert _sentinel("BODY") not in caplog.text


def test_periodic_task_returns_probe_status_and_is_not_part_of_startup(monkeypatch):
    monkeypatch.setattr(
        "apps.core.tasks.aggregate_origin.probe_aggregate_origins",
        lambda: {"status": "unconfigured", "recorded": []},
    )

    assert probe_aggregate_metric_origins() == {"status": "unconfigured", "recorded": []}
    assert not getattr(probe_aggregate_metric_origins, "autoretry_for", None)
    schedule = CELERY_BEAT_SCHEDULE["probe_aggregate_metric_origins"]
    assert schedule["task"] == "apps.core.tasks.aggregate_origin.probe_aggregate_metric_origins"
    assert TASK_ROUTES[schedule["task"]] == "background"
    assert schedule["schedule"].tz is not None
    import apps.core.management.commands.batch_init as batch_init

    startup = inspect.getsource(batch_init) + inspect.getsource(CoreConfig.ready)
    assert "probe_aggregate_metric_origins" not in startup
    assert "AggregatePromqlClient" not in startup


def test_probe_preserves_the_unavailable_error_type(caplog):
    client = _Scripted(_values(apm=AggregateMetricsUnavailable("http"), rum=AggregateMetricsUnavailable("timeout")))
    caplog.set_level(logging.WARNING, logger="app")

    result = probe_aggregate_origins(client, at=PROBE_AT)

    assert result["status"] == "degraded"
    assert caplog.records[0].args == ("apm,rum", "AggregateMetricsUnavailable")
    assert logging.Formatter().format(caplog.records[0]).count("Traceback (most recent call last)") == 1
