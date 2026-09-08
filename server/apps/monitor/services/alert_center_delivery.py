"""Monitor 生命周期事件到告警中心的 transactional outbox。"""

import hashlib
import json
import os
from datetime import timedelta

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorAlert, MonitorAlertCenterDelivery, MonitorPolicy
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


def _env_flag(name, *, default=False):
    return os.getenv(name, "true" if default else "false").lower() in {"1", "true", "yes"}


def _outbox_enabled():
    return _env_flag("MONITOR_ALERT_CENTER_OUTBOX_ENABLED") and bool(os.getenv("ALERTS_PER_EVENT_ACK_TOKEN", ""))


# The receiver must understand per-event acknowledgements before producers start
# writing outbox records.  Keep the producer disabled through mixed-version
# rollouts; operators enable it only after the receiver-first deployment.
ALERT_CENTER_ACK_TOKEN = os.getenv("ALERTS_PER_EVENT_ACK_TOKEN", "")
# outbox 的 shadow/active 两阶段都依赖 receiver-first 的认证生命周期身份；
# 缺少共享凭据时保持旧链路，避免先写入无法与即时投递收敛的代次。
ALERT_CENTER_OUTBOX_ENABLED = _outbox_enabled()
ALERT_CENTER_OUTBOX_DELIVERY_ENABLED = _env_flag("MONITOR_ALERT_CENTER_OUTBOX_DELIVERY_ENABLED")
OUTBOX_BATCH_SIZE = 200
OUTBOX_LEASE_TIMEOUT = timedelta(minutes=5)


def _delivery_fingerprint(alert_id, action, payload):
    source = json.dumps(
        {"alert_id": str(alert_id), "action": action, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def enqueue_alert_center_deliveries(
    alerts,
    action,
    *,
    notifier,
    operator="",
    reason="",
    legacy_ingest_identity=False,
    channel_ids_by_alert=None,
):
    """在调用方事务内保存按 alert/action 代次排序的不可变载荷。"""
    if not ALERT_CENTER_OUTBOX_ENABLED or not alerts:
        return []

    configured_channel_ids = {
        int(value)
        for alert in alerts
        for value in ((channel_ids_by_alert or {}).get(alert.id) or notifier._resolve_notice_type_ids(alert))
        if str(value).isdigit()
    }
    alert_center_channel_ids = set()
    unresolved_channel_ids = set()
    for channel_id in configured_channel_ids:
        try:
            capability = SystemMgmtUtils.probe_notification_channel(channel_id, capability_only=True) or {}
        except Exception:
            # 能力目录是外部可降级依赖。生命周期事务不能因为瞬时 RPC
            # 失败而回滚；保留 backfilled=False，由周期对账有界重试。
            logger.exception(
                "告警中心渠道能力查询失败，等待周期对账: channel_id=%s",
                channel_id,
            )
            unresolved_channel_ids.add(channel_id)
            continue
        if capability.get("delivery_mode") == "alert_event_copy":
            alert_center_channel_ids.add(channel_id)
    alert_channels = {
        alert.id: [
            int(value)
            for value in ((channel_ids_by_alert or {}).get(alert.id) or notifier._resolve_notice_type_ids(alert))
            if str(value).isdigit() and int(value) in alert_center_channel_ids
        ]
        for alert in alerts
    }
    target_alerts = [alert for alert in alerts if alert_channels[alert.id]]
    if not target_alerts:
        if not unresolved_channel_ids:
            MonitorAlert.objects.filter(id__in=[alert.id for alert in alerts]).update(alert_center_delivery_backfilled=True)
        return []

    alert_ids = sorted({alert.id for alert in target_alerts})
    created_ids = []
    with transaction.atomic():
        locked_by_id = {alert.id: alert for alert in MonitorAlert.objects.select_for_update().filter(id__in=alert_ids).order_by("id")}
        instance_org_map = notifier._build_instance_org_map(target_alerts)
        monitor_identity_map = notifier._build_monitor_identity_map(target_alerts)
        for original in target_alerts:
            alert = locked_by_id.get(original.id, original)
            base_payload = notifier._build_alert_center_payload(
                alert,
                action,
                operator,
                reason,
                instance_org_map,
                monitor_identity_map,
            )
            if legacy_ingest_identity:
                # 旧 producer 没有 lifecycle identity。存量 new 的 notified=True
                # 无法区分“已经成功”与“默认值掩盖失败”，沿用旧 ingest key
                # 才能让 receiver 对前者去重、对后者正常接收。
                base_payload.pop("lifecycle_action", None)
            for channel_id in alert_channels[alert.id]:
                blocking_generation = (
                    MonitorAlertCenterDelivery.objects.filter(
                        alert_id=alert.id,
                        channel_id=channel_id,
                        status=MonitorAlertCenterDelivery.Status.FAILED,
                    )
                    .order_by("generation")
                    .values_list("generation", flat=True)
                    .first()
                )
                delivery_id = _delivery_fingerprint(
                    alert.id,
                    action,
                    {"channel_id": channel_id, **base_payload},
                )
                existing = MonitorAlertCenterDelivery.objects.filter(delivery_id=delivery_id).first()
                if existing:
                    continue
                generation = (MonitorAlertCenterDelivery.objects.filter(alert_id=alert.id).aggregate(value=Max("generation"))["value"] or 0) + 1
                payload = {
                    **base_payload,
                    "lifecycle_generation": delivery_id,
                }
                delivery = MonitorAlertCenterDelivery.objects.create(
                    alert_id=alert.id,
                    action=action,
                    generation=generation,
                    delivery_id=delivery_id,
                    channel_id=channel_id,
                    payload=payload,
                    status=(
                        MonitorAlertCenterDelivery.Status.FAILED if blocking_generation is not None else MonitorAlertCenterDelivery.Status.PENDING
                    ),
                    last_error=(f"blocked by terminal generation {blocking_generation}" if blocking_generation is not None else ""),
                )
                created_ids.append(delivery.id)

        if created_ids:
            MonitorAlert.objects.filter(id__in=alert_ids).update(alert_center_notified=False)
            if ALERT_CENTER_OUTBOX_DELIVERY_ENABLED:
                transaction.on_commit(lambda ids=tuple(created_ids): _schedule_deliveries(ids))
        resolved_alert_ids = [
            alert.id
            for alert in target_alerts
            if not unresolved_channel_ids.intersection(
                int(value)
                for value in ((channel_ids_by_alert or {}).get(alert.id) or notifier._resolve_notice_type_ids(alert))
                if str(value).isdigit()
            )
        ]
        if resolved_alert_ids:
            MonitorAlert.objects.filter(id__in=resolved_alert_ids).update(alert_center_delivery_backfilled=True)
    return created_ids


def _schedule_deliveries(delivery_ids):
    from apps.monitor.tasks.monitor_policy import deliver_alert_center_lifecycle_delivery

    for delivery_id in delivery_ids:
        try:
            deliver_alert_center_lifecycle_delivery.delay(delivery_id)
        except Exception:
            logger.exception("告警中心 outbox 调度失败，等待周期补偿: delivery_id=%s", delivery_id)


def _ack_result(send_result, delivery_id):
    if not isinstance(send_result, dict):
        return False, True, "invalid response"
    for item in (send_result.get("data") or {}).get("event_results") or []:
        if isinstance(item, dict) and item.get("delivery_id") == delivery_id:
            status = item.get("status")
            if status in {"accepted", "duplicate"}:
                return True, False, ""
            return False, bool(item.get("retryable", status == "errored")), status or "invalid acknowledgement"
    if send_result.get("result") is True:
        return True, False, ""
    return (
        False,
        bool(send_result.get("retryable", True)),
        send_result.get("code") or send_result.get("message") or "delivery failed",
    )


def deliver_alert_center_delivery(record_id):
    """按代次 claim/finalize；旧执行不能覆盖新 claim，后继动作不得越过前驱。"""
    now = timezone.now()
    alert_id = MonitorAlertCenterDelivery.objects.filter(id=record_id).values_list("alert_id", flat=True).first()
    if alert_id is None:
        return False
    with transaction.atomic():
        # 与 enqueue 保持 alert → delivery 的统一锁顺序；终态传播期间
        # 禁止并发 enqueue 在扫描后插入一个永远被 FAILED 前驱阻塞的后继。
        MonitorAlert.objects.select_for_update().get(id=alert_id)
        record = MonitorAlertCenterDelivery.objects.select_for_update().filter(id=record_id).first()
        if not record or record.status in {record.Status.DELIVERED, record.Status.FAILED}:
            return False
        earlier_unfinished = (
            MonitorAlertCenterDelivery.objects.filter(
                alert_id=record.alert_id,
                channel_id=record.channel_id,
                generation__lt=record.generation,
            )
            .exclude(status=record.Status.DELIVERED)
            .exists()
        )
        if earlier_unfinished:
            return False
        if record.status == record.Status.DELIVERING and record.updated_at > now - OUTBOX_LEASE_TIMEOUT:
            return False
        if record.attempts >= record.max_attempts:
            record.status = record.Status.FAILED
            record.next_retry_at = None
            record.last_error = record.last_error or "retries exhausted"
            record.save(update_fields=["status", "next_retry_at", "last_error", "updated_at"])
            _fail_blocked_successors(record)
            return False
        record.status = record.Status.DELIVERING
        record.attempts += 1
        record.last_error = ""
        record.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        claim_generation = record.attempts
        delivery_id = record.delivery_id
        payload = dict(record.payload)

    payload["delivery_id"] = delivery_id
    try:
        send_result = SystemMgmtUtils.dispatch_notification(
            delivery_key=delivery_id,
            channel_id=record.channel_id,
            organization_ids=payload.get("organizations") or [],
            recipients=[],
            title="",
            body=payload.get("description") or payload.get("title") or "alert event",
            event_payload=payload,
            required_delivery_mode="alert_event_copy",
            producer="lite-monitor",
            ack_mode="per_event_v1",
            ack_token=ALERT_CENTER_ACK_TOKEN,
            internal_caller="lite-monitor",
        )
        success, retryable, error = _ack_result(send_result, delivery_id)
    except Exception as exc:
        logger.exception(
            "告警中心 outbox 投递异常: delivery_id=%s channel_id=%s",
            delivery_id,
            record.channel_id,
        )
        success, retryable, error = False, True, str(exc)

    finished_at = timezone.now()
    if success:
        with transaction.atomic():
            # Enqueue takes the same alert-row lock. This makes finalization and
            # the "all generations delivered" decision one ordered state change.
            MonitorAlert.objects.select_for_update().get(id=record.alert_id)
            finalized = MonitorAlertCenterDelivery.objects.filter(
                id=record_id,
                status=MonitorAlertCenterDelivery.Status.DELIVERING,
                attempts=claim_generation,
            ).update(
                status=MonitorAlertCenterDelivery.Status.DELIVERED,
                delivered_at=finished_at,
                next_retry_at=None,
                last_error="",
                updated_at=finished_at,
            )
            if (
                finalized
                and not MonitorAlertCenterDelivery.objects.filter(alert_id=record.alert_id)
                .exclude(status=MonitorAlertCenterDelivery.Status.DELIVERED)
                .exists()
            ):
                MonitorAlert.objects.filter(id=record.alert_id).update(alert_center_notified=True, alert_center_retry_count=0)
        return bool(finalized)

    terminal = not retryable or claim_generation >= record.max_attempts
    next_status = MonitorAlertCenterDelivery.Status.FAILED if terminal else MonitorAlertCenterDelivery.Status.PENDING
    next_retry_at = None if terminal else finished_at + timedelta(seconds=min(3600, 15 * (2 ** min(claim_generation, 8))))
    with transaction.atomic():
        if terminal:
            # 与 enqueue 共用 alert 行锁；终态传播扫描和提交之间不允许
            # 并发插入一个看不到 FAILED 前驱的 PENDING 后继。
            MonitorAlert.objects.select_for_update().get(id=record.alert_id)
        finalized = MonitorAlertCenterDelivery.objects.filter(
            id=record_id,
            status=MonitorAlertCenterDelivery.Status.DELIVERING,
            attempts=claim_generation,
        ).update(
            status=next_status,
            next_retry_at=next_retry_at,
            last_error=error[:2000],
            updated_at=finished_at,
        )
        if finalized and terminal:
            record.status = MonitorAlertCenterDelivery.Status.FAILED
            _fail_blocked_successors(record)
    return False


def _fail_blocked_successors(record):
    """A terminal predecessor makes later lifecycle copies unsafe to deliver."""
    MonitorAlertCenterDelivery.objects.filter(
        alert_id=record.alert_id,
        channel_id=record.channel_id,
        generation__gt=record.generation,
        status__in=[
            MonitorAlertCenterDelivery.Status.PENDING,
            MonitorAlertCenterDelivery.Status.DELIVERING,
        ],
    ).update(
        status=MonitorAlertCenterDelivery.Status.FAILED,
        next_retry_at=None,
        last_error=f"blocked by terminal generation {record.generation}",
        updated_at=timezone.now(),
    )


def backfill_legacy_alerts():
    """有界对账存量告警；成功旧投递会由接收端幂等去重。"""
    alerts = list(
        MonitorAlert.objects.filter(alert_center_delivery_backfilled=False)
        .filter(Q(alert_center_notified=False) | Q(status="new"))
        .order_by("id")[:OUTBOX_BATCH_SIZE]
    )
    if not alerts:
        return 0
    policies = MonitorPolicy.objects.in_bulk({alert.policy_id for alert in alerts if alert.policy_id})
    from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier

    for alert in alerts:
        policy = policies.get(alert.policy_id)
        configured_ids = [int(value) for value in alert.notice_type_ids or [] if str(value).isdigit()]
        if not configured_ids and policy is not None:
            configured_ids = [int(value) for value in policy.notice_type_ids or [] if str(value).isdigit()]
        successful_created_channel_ids = {
            int(entry.get("channel_id"))
            for entry in alert.notice_logs or []
            if isinstance(entry, dict)
            and entry.get("action") in {"created", "upgraded"}
            and entry.get("success") is True
            and str(entry.get("channel_id")).isdigit()
        }
        if policy is not None and not policy.notice:
            configured_ids = [
                channel_id
                for channel_id in configured_ids
                if alert.status in {"recovered", "closed"} and channel_id in successful_created_channel_ids
            ]
        if not configured_ids:
            MonitorAlert.objects.filter(id=alert.id).update(alert_center_delivery_backfilled=True)
            continue
        notifier = AlertLifecycleNotifier(policy, policies_by_id=policies)
        missing_created_channel_ids = sorted(set(configured_ids) - successful_created_channel_ids)
        if alert.status != "new" and missing_created_channel_ids:
            # 存量只有当前态，没有首次告警的不可变快照；先建立兼容 created
            # 前驱，保证 recovery/closed 不会越过尚未确认的首次投递。
            enqueue_alert_center_deliveries(
                [alert],
                "created",
                notifier=notifier,
                legacy_ingest_identity=True,
                channel_ids_by_alert={alert.id: missing_created_channel_ids},
            )
        enqueue_alert_center_deliveries(
            [alert],
            "created" if alert.status == "new" else alert.status,
            notifier=notifier,
            legacy_ingest_identity=(alert.status == "new" and alert.alert_center_notified),
            channel_ids_by_alert={alert.id: configured_ids},
        )
    return len(alerts)


def due_delivery_ids():
    now = timezone.now()
    stale_before = now - OUTBOX_LEASE_TIMEOUT
    return list(
        MonitorAlertCenterDelivery.objects.filter(
            Q(status=MonitorAlertCenterDelivery.Status.PENDING)
            | Q(status=MonitorAlertCenterDelivery.Status.DELIVERING, updated_at__lte=stale_before),
            Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now),
        )
        .order_by("alert_id", "generation")
        .values_list("id", flat=True)[:OUTBOX_BATCH_SIZE]
    )
