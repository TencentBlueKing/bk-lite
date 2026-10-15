import logging

import pytest

from apps.monitor.constants.license_catalog import MONITOR_LICENSE_OBJECT_NAMES
from apps.monitor.nats import monitor as nm


class _FakeQuerySet:
    def __init__(self, rows):
        self.rows = rows
        self.filter_kwargs = None

    def filter(self, **kwargs):
        self.filter_kwargs = kwargs
        return self

    def values(self, *args):
        return self

    def annotate(self, **kwargs):
        return self.rows


def _assert_safe_warning(record, message, args, sentinel, original):
    assert record.msg == message
    assert record.args == args
    assert sentinel not in record.getMessage()
    exc_type, exc_value, exc_tb = record.exc_info
    assert exc_type.__name__ == "SafeLogException"
    assert str(exc_value) == type(original).__name__
    assert exc_value is not original
    assert exc_tb is original.__traceback__
    assert str(original) == sentinel
    rendered = logging.Formatter().format(record)
    assert sentinel not in rendered
    assert "Traceback" in rendered


class _FakeLanguageLoader:
    constructed = False

    def __init__(self, app, default_lang=None):
        type(self).constructed = True
        self.app = app
        self.default_lang = default_lang

    def get(self, key, default=None):
        return {"monitor_object.Host": "主机"}.get(key, default)


@pytest.mark.unit
def test_license_monitor_instance_count_filters_active_catalog_objects(monkeypatch):
    fake_qs = _FakeQuerySet(
        [
            {"monitor_object__name": "Host", "instance_count": 2},
            {"monitor_object__name": "Mysql", "instance_count": 1},
        ]
    )
    monkeypatch.setattr(nm.MonitorInstance.objects, "filter", fake_qs.filter)
    monkeypatch.setattr(
        nm.MonitorObject.objects,
        "filter",
        lambda **kwargs: type("Rows", (), {"values_list": lambda self, *args: [("Host", ""), ("Mysql", "MySQL")]})(),
    )
    monkeypatch.setattr("apps.core.utils.loader.LanguageLoader", _FakeLanguageLoader)
    _FakeLanguageLoader.constructed = False

    out = nm.license_monitor_instance_count(language="zh-Hans")

    assert _FakeLanguageLoader.constructed is True

    assert out["data"] == {"Host": 2, "Mysql": 1}
    assert out["labels"] == {"Host": "主机", "Mysql": "MySQL"}
    assert fake_qs.filter_kwargs["is_deleted"] is False
    assert fake_qs.filter_kwargs["is_active"] is True
    assert set(fake_qs.filter_kwargs["monitor_object__name__in"]) == set(MONITOR_LICENSE_OBJECT_NAMES)
    assert "Pod" not in fake_qs.filter_kwargs["monitor_object__name__in"]
    assert "TCP" not in fake_qs.filter_kwargs["monitor_object__name__in"]


@pytest.mark.unit
def test_license_monitor_labels_failure_keeps_counts(monkeypatch, caplog):
    sentinel = "SECRET-MONITOR-LABEL-PAYLOAD"
    fake_qs = _FakeQuerySet([{"monitor_object__name": "Host", "instance_count": 2}])
    monkeypatch.setattr(nm.MonitorInstance.objects, "filter", fake_qs.filter)

    raised = {}

    def fail_filter(**kwargs):
        error = RuntimeError(sentinel)
        raised["error"] = error
        raise error

    monkeypatch.setattr(nm.MonitorObject.objects, "filter", fail_filter)
    monkeypatch.setattr("apps.core.utils.loader.LanguageLoader", _FakeLanguageLoader)

    with caplog.at_level(logging.WARNING, logger="monitor"):
        out = nm.license_monitor_instance_count(language=None)

    assert out["data"] == {"Host": 2}
    assert out["labels"] == {}
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    _assert_safe_warning(
        warnings[0],
        "event=license_monitor_labels_skipped failed_stage=%s error_type=%s",
        ("resolve_labels", "RuntimeError"),
        sentinel,
        raised["error"],
    )
    assert sentinel not in caplog.text


@pytest.mark.unit
def test_license_monitor_missing_language_uses_user_locale_only(monkeypatch):
    seen = {}

    class _SeenLoader:
        def __init__(self, app, default_lang=None):
            seen["language"] = default_lang

        def get(self, key, default=None):
            return None

    fake_qs = _FakeQuerySet([{"monitor_object__name": "Host", "instance_count": 1}])
    monkeypatch.setattr(nm.MonitorInstance.objects, "filter", fake_qs.filter)
    monkeypatch.setattr(
        nm.MonitorObject.objects,
        "filter",
        lambda **kwargs: type("Rows", (), {"values_list": lambda self, *args: [("Host", "")]})(),
    )
    monkeypatch.setattr("apps.core.utils.loader.LanguageLoader", _SeenLoader)

    out = nm.license_monitor_instance_count(user_info={"language": "en", "LANGUAGE_CODE": "en"})
    assert seen["language"] is None
    assert out["data"] == {"Host": 1}
    assert out["labels"] == {"Host": "Host"}

    nm.license_monitor_instance_count(user_info={"locale": "en", "language": "zh-Hans"})
    assert seen["language"] == "en"
