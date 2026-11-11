import logging
from datetime import UTC, datetime

from apps.apm.adapters.aggregate_red import align_query_end as align_apm_query_end
from apps.core.aggregate_promql import align_query_end, apm_flush_seconds, rum_flush_seconds

ENDED = datetime(2026, 11, 10, 0, 16, 30, tzinfo=UTC)
DEFAULT_APM_END = datetime(2026, 11, 10, 0, 15, tzinfo=UTC)
DEFAULT_RUM_END = datetime(2026, 11, 10, 0, 15, tzinfo=UTC)
_TEMPLATE = "event=aggregate_flush_interval_invalid name=%s default_seconds=%s"


def _aligned(seconds: int) -> datetime:
    return align_query_end(ENDED, now=ENDED, flush_seconds=seconds)


def _warnings(call):
    records = []
    handler = logging.Handler()
    handler.setLevel(logging.WARNING)
    handler.emit = records.append
    app_logger = logging.getLogger("app")
    previous = app_logger.level
    app_logger.setLevel(logging.WARNING)
    app_logger.addHandler(handler)
    try:
        result = call()
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(previous)
    return result, [record for record in records if record.msg == _TEMPLATE]


def test_unset_intervals_use_the_collector_defaults(monkeypatch):
    monkeypatch.delenv("APM_AGG_FLUSH_INTERVAL", raising=False)
    monkeypatch.delenv("RUM_AGG_BATCH_TIMEOUT", raising=False)

    (apm_seconds, rum_seconds), records = _warnings(lambda: (apm_flush_seconds(), rum_flush_seconds()))

    assert apm_seconds == 60
    assert rum_seconds == 60
    assert _aligned(apm_seconds) == DEFAULT_APM_END
    assert _aligned(rum_seconds) == DEFAULT_RUM_END
    assert records == []


def test_custom_intervals_move_the_aligned_end(monkeypatch):
    monkeypatch.setenv("APM_AGG_FLUSH_INTERVAL", "30s")
    monkeypatch.setenv("RUM_AGG_BATCH_TIMEOUT", "10s")

    assert apm_flush_seconds() == 30
    assert rum_flush_seconds() == 10
    assert _aligned(apm_flush_seconds()) == datetime(2026, 11, 10, 0, 15, 30, tzinfo=UTC)
    assert _aligned(rum_flush_seconds()) == datetime(2026, 11, 10, 0, 15, 50, tzinfo=UTC)
    assert align_apm_query_end(ENDED, now=ENDED) == datetime(2026, 11, 10, 0, 15, 30, tzinfo=UTC)


def test_collector_duration_shapes_round_up_to_whole_seconds(monkeypatch):
    monkeypatch.setenv("APM_AGG_FLUSH_INTERVAL", "1m30s")
    monkeypatch.setenv("RUM_AGG_BATCH_TIMEOUT", "1h2m3s")

    assert apm_flush_seconds() == 90
    assert rum_flush_seconds() == 3723
    assert _aligned(90) == datetime(2026, 11, 10, 0, 14, 30, tzinfo=UTC)

    monkeypatch.setenv("APM_AGG_FLUSH_INTERVAL", "1500ms")
    assert apm_flush_seconds() == 2

    monkeypatch.setenv("APM_AGG_FLUSH_INTERVAL", "500ms")
    assert apm_flush_seconds() == 1


def test_invalid_interval_uses_the_default_and_warns_once(monkeypatch):
    sentinel = "redis://:super-secret-password@10.9.8.7:6379/0\ntoken=secret"
    monkeypatch.setenv("APM_AGG_FLUSH_INTERVAL", sentinel)

    def read_twice():
        return apm_flush_seconds(), apm_flush_seconds(), _aligned(apm_flush_seconds())

    (first, second, aligned), records = _warnings(read_twice)

    assert first == second == 60
    assert aligned == DEFAULT_APM_END
    assert len(records) == 1
    record = records[0]
    assert record.name == "app"
    assert record.levelno == logging.WARNING
    assert record.msg == _TEMPLATE
    assert record.args == ("APM_AGG_FLUSH_INTERVAL", 60)
    assert record.exc_info is None
    rendered = record.getMessage()
    formatted = logging.Formatter().format(record)
    assert rendered == "event=aggregate_flush_interval_invalid name=APM_AGG_FLUSH_INTERVAL default_seconds=60"
    for secret in (sentinel, "super-secret-password", "10.9.8.7", "token=secret", "redis://"):
        assert secret not in rendered
        assert secret not in formatted
        assert secret not in str(record.args)
    assert "\n" not in rendered
