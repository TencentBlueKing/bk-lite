import pytest
from django.db import IntegrityError, transaction

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models import ActiveAlertFingerprint, Alert


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
