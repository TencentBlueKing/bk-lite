"""周期评估终态汇总与通知投递意图。"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from apps.patch_mgmt.constants import ComplianceStatus, GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import AssessmentNotificationDelivery, HostBaselineBinding
from apps.patch_mgmt.utils.i18n import patch_message


def _assessment_summary(task) -> dict:
    host_rows = list(task.host_results.values("target_id", "stage"))
    task_target_ids = {int(target_id) for target_id in (task.target_list or [])}
    host_target_ids = {int(row["target_id"]) for row in host_rows}
    all_target_ids = task_target_ids | host_target_ids
    failed_target_ids = {int(row["target_id"]) for row in host_rows if row["stage"] in {"failed", "reboot_failed"}}
    completed_target_ids = {int(row["target_id"]) for row in host_rows if row["stage"] == "completed"}
    if task.status in {
        GovernanceTaskStatus.FAILED,
        GovernanceTaskStatus.PARTIAL_SUCCESS,
    }:
        failed_target_ids.update(all_target_ids - completed_target_ids)
    binding_rows = HostBaselineBinding.objects.filter(target_id__in=completed_target_ids).values("target_id", "compliance_status")
    non_compliant_count = 0
    binding_failed_target_ids = set()
    for row in binding_rows:
        status = row["compliance_status"]
        if status == ComplianceStatus.NON_COMPLIANT:
            non_compliant_count += 1
        elif status in {ComplianceStatus.FAILED, ComplianceStatus.UNKNOWN}:
            binding_failed_target_ids.add(int(row["target_id"]))

    return {
        "total_count": len(all_target_ids),
        "non_compliant_count": non_compliant_count,
        "failed_count": len(failed_target_ids | binding_failed_target_ids),
    }


def _format_notification(task, summary: dict) -> tuple[str, str]:
    finished_at = task.finished_at or timezone.now()
    timezone_name = (task.notification_snapshot or {}).get("timezone")
    try:
        target_timezone = ZoneInfo(timezone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        target_timezone = timezone.get_default_timezone()
    local_finished_at = timezone.localtime(finished_at, target_timezone).strftime("%Y-%m-%d %H:%M:%S")
    title = patch_message(
        None,
        "message.periodic_assessment_title",
        "[Patch Management] Periodic assessment found items that need attention",
    )
    content = "\n".join(
        [
            patch_message(None, "message.periodic_assessment_done", "Periodic assessment completed."),
            patch_message(
                None,
                "message.periodic_assessment_finished_at",
                "Completed at: {time}",
                time=local_finished_at,
            ),
            patch_message(
                None,
                "message.periodic_assessment_total_hosts",
                "Total hosts: {count}",
                count=summary["total_count"],
            ),
            patch_message(
                None,
                "message.periodic_assessment_non_compliant",
                "Non-compliant hosts: {count}",
                count=summary["non_compliant_count"],
            ),
            patch_message(
                None,
                "message.periodic_assessment_failed_hosts",
                "Failed hosts: {count}",
                count=summary["failed_count"],
            ),
        ]
    )
    return title, content


def enqueue_periodic_assessment_notifications(task, *, schedule: bool = True) -> list[int]:
    """幂等地为周期评估生成每渠道一条投递意图。"""
    snapshot = task.notification_snapshot or {}
    rules = snapshot.get("rules") or []
    if task.task_type != GovernanceTaskType.ASSESS or task.trigger_source != "periodic_scan" or not snapshot.get("enabled") or not rules:
        return []

    summary = _assessment_summary(task)
    if not summary["non_compliant_count"] and not summary["failed_count"]:
        return []
    title, content = _format_notification(task, summary)

    delivery_ids = []
    with transaction.atomic():
        for rule in rules:
            delivery, _ = AssessmentNotificationDelivery.objects.get_or_create(
                task=task,
                channel_id=int(rule["channel_id"]),
                defaults={
                    "channel_name": str(rule.get("channel_name") or ""),
                    "channel_type": str(rule.get("channel_type") or ""),
                    "receivers": list(rule.get("receivers") or []),
                    "team_id": int(rule.get("team_id") or 0),
                    "title": title,
                    "content": content,
                    "summary": summary,
                },
            )
            if delivery.status in {
                AssessmentNotificationDelivery.Status.PENDING,
                AssessmentNotificationDelivery.Status.RETRY,
            }:
                delivery_ids.append(delivery.id)

        if delivery_ids and schedule:
            transaction.on_commit(lambda ids=tuple(delivery_ids): _dispatch_deliveries(ids))
    return delivery_ids


def reconcile_periodic_assessment_notification_intent(task, *, schedule: bool = True) -> list[int]:
    """生成通知意图并标记已对账；无需通知也应标记，避免重复扫描。"""
    from apps.patch_mgmt.models import GovernanceTask

    delivery_ids = enqueue_periodic_assessment_notifications(
        task,
        schedule=schedule,
    )
    reconciled_at = timezone.now()
    GovernanceTask.objects.filter(pk=task.pk).update(
        notification_reconciled_at=reconciled_at,
        updated_at=reconciled_at,
    )
    task.notification_reconciled_at = reconciled_at
    return delivery_ids


def _dispatch_deliveries(delivery_ids: tuple[int, ...]) -> None:
    from apps.patch_mgmt.tasks import send_assessment_notification_delivery

    for delivery_id in delivery_ids:
        send_assessment_notification_delivery.delay(delivery_id)
