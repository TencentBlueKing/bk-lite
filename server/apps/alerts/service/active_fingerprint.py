from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.active_fingerprint import ActiveAlertFingerprint
from apps.alerts.models.models import Alert


def claim_active_fingerprint(fingerprint: str):
    """锁定指纹租约并返回 ``(lease, active_alert)``；必须在 atomic 内调用。"""
    lease, _ = ActiveAlertFingerprint.objects.get_or_create(fingerprint=fingerprint)
    lease = (
        ActiveAlertFingerprint.objects.select_for_update()
        .select_related("alert")
        .get(pk=lease.pk)
    )
    if lease.alert_id and lease.alert.status in AlertStatus.ACTIVATE_STATUS:
        return lease, lease.alert

    legacy_alert = (
        Alert.objects.filter(
            fingerprint=fingerprint, status__in=AlertStatus.ACTIVATE_STATUS
        )
        .order_by("-updated_at")
        .first()
    )
    if legacy_alert:
        bind_active_fingerprint(lease, legacy_alert)
        return lease, legacy_alert
    return lease, None


def bind_active_fingerprint(lease: ActiveAlertFingerprint, alert: Alert) -> None:
    lease.alert = alert
    lease.save(update_fields=["alert", "updated_at"])
