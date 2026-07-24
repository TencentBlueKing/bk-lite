import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models import ActiveAlertFingerprint, Alert
from apps.alerts.service.active_fingerprint import claim_active_fingerprint


@pytest.mark.django_db
def test_active_fingerprint_lease_is_database_unique():
    ActiveAlertFingerprint.objects.create(fingerprint="fp-shared")

    with pytest.raises(IntegrityError), transaction.atomic():
        ActiveAlertFingerprint.objects.create(fingerprint="fp-shared")


@pytest.mark.django_db
def test_closing_alert_releases_active_fingerprint_lease():
    alert = Alert.objects.create(
        alert_id="A-LEASE-1",
        fingerprint="fp-release",
        title="t",
        content="c",
        level="0",
        status=AlertStatus.UNASSIGNED,
    )
    lease = ActiveAlertFingerprint.objects.create(fingerprint=alert.fingerprint, alert=alert)

    alert.status = AlertStatus.CLOSED
    alert.save(update_fields=["status", "updated_at"])

    assert not ActiveAlertFingerprint.objects.filter(pk=lease.pk).exists()


@pytest.mark.django_db
def test_claim_empty_fingerprint_lease_does_not_join_nullable_alert():
    """锁指纹租约时不能外连接可空 Alert，否则 PostgreSQL 会拒绝 FOR UPDATE。"""
    ActiveAlertFingerprint.objects.create(fingerprint="fp-empty")

    with CaptureQueriesContext(connection) as queries:
        with transaction.atomic():
            lease, alert = claim_active_fingerprint("fp-empty")

    assert lease.fingerprint == "fp-empty"
    assert alert is None
    assert not any(
        "JOIN" in query["sql"].upper()
        and "ALERTS_ALERT" in query["sql"].upper()
        for query in queries.captured_queries
    )
