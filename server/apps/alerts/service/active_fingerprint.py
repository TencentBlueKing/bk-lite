from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.active_fingerprint import ActiveAlertFingerprint
from apps.alerts.models.models import Alert


def claim_active_fingerprint(fingerprint: str):
    """锁定指纹租约并返回 ``(lease, active_alert)``；必须在 atomic 内调用。"""
    lease, _ = ActiveAlertFingerprint.objects.get_or_create(fingerprint=fingerprint)
    # 只锁定作为并发租约的主表记录。alert 是可空关联，select_related 会生成
    # LEFT OUTER JOIN；PostgreSQL 不允许 FOR UPDATE 锁定外连接的可空侧。
    lease = ActiveAlertFingerprint.objects.select_for_update().get(pk=lease.pk)
    active_alert = (
        Alert.objects.filter(pk=lease.alert_id).first()
        if lease.alert_id
        else None
    )
    if active_alert and active_alert.status in AlertStatus.ACTIVATE_STATUS:
        return lease, active_alert

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
