"""init_alert_sources：内置告警源新建与字段变更更新。"""
import pytest
from django.core.management import call_command

from apps.alerts.constants.init_data import BUILTIN_ALERT_SOURCES
from apps.alerts.models.alert_source import AlertSource

pytestmark = pytest.mark.django_db


def test_init_alert_sources_creates_then_updates_changed_fields():
    builtin_ids = [src["source_id"] for src in BUILTIN_ALERT_SOURCES]
    assert "restful" in builtin_ids

    call_command("init_alert_sources")
    created = {src.source_id: src for src in AlertSource.all_objects.filter(source_id__in=builtin_ids)}
    assert set(created) == set(builtin_ids)
    restful = created["restful"]
    assert restful.name == "RESTful"
    assert restful.is_active is True

    restful.name = "RESTful-old"
    restful.save(update_fields=["name"])
    call_command("init_alert_sources")
    restful.refresh_from_db()
    assert restful.name == "RESTful"
    assert AlertSource.all_objects.filter(source_id="restful").count() == 1
