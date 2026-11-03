import pytest
from django.core.management import call_command

from apps.system_mgmt.models import Channel, IMNotificationChannel, NotificationTag

pytestmark = pytest.mark.django_db


def test_init_notification_tags_inserts_catalog_rows_and_rerun_keeps_them():
    NotificationTag.objects.filter(key="system", value="itsm").delete()

    call_command("init_notification_tags")
    call_command("init_notification_tags")

    rows = list(NotificationTag.objects.filter(key="system", value="itsm").order_by("id"))
    assert [(row.key, row.value) for row in rows] == [("system", "itsm")]
    assert rows[0].created_by == "system"
    assert rows[0].domain == "domain.com"
    assert Channel.objects.filter(tags__in=rows).count() == 0
    assert IMNotificationChannel.objects.filter(tags__in=rows).count() == 0


def test_init_notification_tags_keeps_an_existing_row():
    NotificationTag.objects.filter(key="system", value="itsm").delete()
    kept = NotificationTag.objects.create(key="system", value="itsm", created_by="kept-operator", domain="kept.example")

    call_command("init_notification_tags")

    kept.refresh_from_db()
    assert NotificationTag.objects.filter(key="system", value="itsm").count() == 1
    assert kept.created_by == "kept-operator"
    assert kept.domain == "kept.example"
