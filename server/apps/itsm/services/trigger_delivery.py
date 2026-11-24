from datetime import timedelta
from functools import partial

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.logger import itsm_logger as logger
from apps.core.logger import safe_exception_info
from apps.itsm.models import TriggerLog
from apps.itsm.services.notify.service import dispatch_notification, send_im_channel
from apps.itsm.services.trigger_notice import NoticeClaimLost, TriggerNotice, deliver_configured_notice

LEASE_DURATION = timedelta(minutes=5)
MAX_ATTEMPTS = 3


def schedule_delivery(log_id):
    transaction.on_commit(partial(deliver_trigger_notice, log_id), robust=True)


def _due_notices(now):
    return TriggerLog.objects.filter(status=TriggerLog.Status.PENDING, action="notice", delivery_payload__isnull=False).filter(
        Q(delivery_claimed_at__isnull=True) | Q(delivery_claimed_at__lt=now - LEASE_DURATION)
    )


def drain_trigger_notices(limit=10):
    ids = list(_due_notices(timezone.now()).order_by("pk").values_list("pk", flat=True)[:limit])
    for log_id in ids:
        deliver_trigger_notice(log_id)


def deliver_trigger_notice(log_id):
    now = timezone.now()
    due = _due_notices(now).filter(pk=log_id)
    stage = "claim"
    try:
        due.filter(delivery_attempts__gte=MAX_ATTEMPTS).update(
            status=TriggerLog.Status.FAILED,
            message="通知恢复次数已用完，请核对发送结果",
            delivery_payload=None,
            delivery_receipts={},
            delivery_claimed_at=None,
        )
        if not due.filter(delivery_attempts__lt=MAX_ATTEMPTS).update(delivery_claimed_at=now, delivery_attempts=F("delivery_attempts") + 1):
            return
        claimed = TriggerLog.objects.filter(pk=log_id, status=TriggerLog.Status.PENDING, delivery_claimed_at=now)
        stage = "load_snapshot"
        log = claimed.get()
        stage = "deliver"
        success, message = _dispatch(log, claimed)
        stage = "persist"
        claimed.update(
            status=TriggerLog.Status.SUCCESS if success else TriggerLog.Status.FAILED,
            message=message,
            delivery_payload=None,
            delivery_receipts={},
            delivery_claimed_at=None,
        )
    except NoticeClaimLost:
        return
    except Exception as error:
        logger.error(
            "触发器通知处理失败 log=%s failed_stage=%s error_type=%s",
            log_id,
            stage,
            type(error).__name__,
            exc_info=safe_exception_info(error),
        )


def _dispatch(log, claimed):
    payload = log.delivery_payload
    event_key = f"itsm-trigger-{log.pk}"
    variables, recipients = payload["variables"], payload["recipients"]
    sender = partial(_guarded_im, claimed, event_key, payload["notice"] is None)
    if payload["notice"] is not None:
        return deliver_configured_notice(
            TriggerNotice.model_validate(payload["notice"]),
            variables,
            recipients,
            domain=log.domain,
            event_key=event_key,
            is_test=payload["is_test"],
            im_sender=sender,
        )

    result = dispatch_notification(
        "trigger",
        variables,
        recipients,
        event_key=event_key,
        site_only=payload["is_test"],
        domain=log.domain,
        im_link=variables["ticket_link"],
        im_sender=sender,
    )
    site, im = result["site"], result["im"]
    if not site.get("result"):
        return False, "通知发送失败"
    if im.get("unknown"):
        return False, "站内通知已发送，即时消息投递结果未知，请核对"
    if im.get("partial_success") or (not im.get("result") and not im.get("skipped")):
        return False, "站内通知已发送，即时消息投递失败"
    return True, "已发送站内通知和即时消息" if im.get("result") else "已发送站内通知"


def _guarded_im(claimed, event_key, legacy_route, channel_id, title, content, user_ids):
    route = "legacy" if legacy_route else str(channel_id)
    keys = {user_id: f"{route}:{user_id}" for user_id in user_ids}
    with transaction.atomic():
        receipts = claimed.select_for_update().values_list("delivery_receipts", flat=True).first()
        if receipts is None:
            raise NoticeClaimLost()
        unsent = [user_id for user_id, key in keys.items() if key not in receipts]
        if unsent:
            # 通道不支持幂等键。先记录发送占位，重启后只继续未尝试的收件人。
            receipts.update({keys[user_id]: "unknown" for user_id in unsent})
            claimed.update(delivery_receipts=receipts)
    if unsent:
        outcome = "unknown"
        try:
            response = send_im_channel(channel_id, title, content, unsent, raise_on_error=True)
            result = response.get("data") or {}
            if not (result.get("partial_success") or result.get("retryable")):
                outcome = "sent" if response.get("result") else "failed"
        except Exception as error:
            logger.error(
                "触发器即时通知结果未知 event_key=%s channel_id=%s failed_stage=dispatch_im error_type=%s",
                event_key,
                channel_id,
                type(error).__name__,
                exc_info=safe_exception_info(error),
            )
        receipts.update({keys[user_id]: outcome for user_id in unsent})
        if not claimed.update(delivery_receipts=receipts):
            raise NoticeClaimLost()

    outcomes = {receipts[key] for key in keys.values()}
    return {
        "result": outcomes == {"sent"},
        "unknown": "unknown" in outcomes,
        "data": {"partial_success": "sent" in outcomes and len(outcomes) > 1},
    }
