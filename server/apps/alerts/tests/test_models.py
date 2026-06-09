"""告警中心模型方法覆盖测试。

对照 spec/prd/告警中心：事件接入幂等键、告警时间格式化、级别展示。
"""

import pytest
from django.utils import timezone

from apps.alerts.models.models import Alert, Event, Incident, Level


@pytest.fixture
def source(db):
    from apps.alerts.models.alert_source import AlertSource

    return AlertSource.objects.create(name="s", source_id="s1", source_type="restful", secret="x")


def test_build_ingest_key_none_when_missing():
    assert Event.build_ingest_key(None, "p", "ext", "created", timezone.now()) is None


def test_build_ingest_key_stable():
    now = timezone.now()
    k1 = Event.build_ingest_key("s1", "p", "ext", "created", now)
    k2 = Event.build_ingest_key("s1", "p", "ext", "created", now)
    assert k1 == k2 and len(k1) == 64


@pytest.mark.django_db
def test_event_save_calculates_ingest_key(source):
    ev = Event.objects.create(
        source=source, raw_data={}, title="t", level="0", start_time=timezone.now(),
        event_id="E1", external_id="ext", action="created",
    )
    assert ev.ingest_key  # save() 自动计算


@pytest.mark.django_db
def test_event_str(source):
    ev = Event.objects.create(source=source, raw_data={}, title="标题", level="0", start_time=timezone.now(), event_id="E1")
    assert "标题" in str(ev)


@pytest.mark.django_db
def test_alert_model_fields():
    fields = Alert.model_fields()
    assert "alert_id" in fields
    assert "status" in fields


@pytest.mark.django_db
def test_alert_format_created_at():
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    formatted = alert.format_created_at()
    assert isinstance(formatted, str)
    # 指定时区字符串
    formatted_tz = alert.format_created_at("Asia/Shanghai")
    assert isinstance(formatted_tz, str)


@pytest.mark.django_db
def test_alert_str():
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    assert "A1" in str(alert)


@pytest.mark.django_db
def test_incident_str_and_format_created_at():
    inc = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp")
    assert "I1" in str(inc)
    assert isinstance(inc.format_created_at, str)


@pytest.mark.django_db
def test_level_str():
    level = Level.objects.create(level_id=0, level_name="Critical", level_display_name="严重", level_type="alert")
    assert "Critical" in str(level)
