import pytest

from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models import MonitorAlert, MonitorEvent
from apps.monitor.models.monitor_object import MonitorInstance


@pytest.mark.django_db
def test_monitor_alert_snapshot_columns_match_instance_width():
    assert MonitorInstance._meta.get_field("id").max_length == MonitorObjConstants.INSTANCE_ID_MAX_LENGTH
    assert MonitorInstance._meta.get_field("name").max_length == MonitorObjConstants.INSTANCE_NAME_MAX_LENGTH
    assert MonitorAlert._meta.get_field("monitor_instance_id").max_length == MonitorObjConstants.INSTANCE_ID_MAX_LENGTH
    assert MonitorAlert._meta.get_field("monitor_instance_name").max_length == MonitorObjConstants.INSTANCE_NAME_MAX_LENGTH
    assert MonitorEvent._meta.get_field("monitor_instance_id").max_length == MonitorObjConstants.INSTANCE_ID_MAX_LENGTH


@pytest.mark.django_db
def test_monitor_alert_persists_names_longer_than_100_chars():
    instance_id = "i" * 101
    instance_name = "n" * 101

    alert = MonitorAlert.objects.create(
        policy_id=1,
        monitor_instance_id=instance_id,
        monitor_instance_name=instance_name,
        level="warning",
        status="new",
    )
    alert.refresh_from_db()

    assert alert.monitor_instance_id == instance_id
    assert alert.monitor_instance_name == instance_name
