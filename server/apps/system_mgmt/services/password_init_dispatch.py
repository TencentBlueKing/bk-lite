"""用户同步初始密码邮件的批次投递状态服务。"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import UserSyncRun


PASSWORD_EMAIL_BATCH_SIZE = 200
PASSWORD_EMAIL_LEASE_SECONDS = 600


def claim_password_email_batch(run_id: int, batch_size: int = PASSWORD_EMAIL_BATCH_SIZE) -> list[dict]:
    """原子领取一批待投递用户，避免同一用户被并发任务重复发送。"""
    with transaction.atomic():
        run = UserSyncRun.objects.select_for_update().filter(id=run_id).first()
        if not run:
            return []
        payload = dict(run.payload or {})
        dispatch = dict(payload.get("email_dispatch", {}))
        pending = list(dispatch.get("pending", []))
        claimed = pending[:batch_size]
        if not claimed:
            return []
        lease_expires_at = (timezone.now() + timedelta(seconds=PASSWORD_EMAIL_LEASE_SECONDS)).isoformat()
        inflight = list(dispatch.get("inflight", []))
        inflight.extend({**item, "lease_expires_at": lease_expires_at} for item in claimed)
        dispatch.update({"pending": pending[batch_size:], "inflight": inflight})
        payload["email_dispatch"] = dispatch
        run.payload = payload
        run.save(update_fields=["payload"])
        return claimed


def complete_password_email_batch(run_id: int, outcomes: list[dict]) -> bool:
    """一次性回写一批终态邮件结果并清理对应加密密码。"""
    with transaction.atomic():
        run = UserSyncRun.objects.select_for_update().filter(id=run_id).first()
        if not run:
            return False
        payload = dict(run.payload or {})
        vault = dict(payload.get("password_vault", {}))
        dispatch = dict(payload.get("email_dispatch", {}))
        outcome_names = {item["username"] for item in outcomes}
        dispatch["inflight"] = [item for item in dispatch.get("inflight", []) if item.get("username") not in outcome_names]
        status = dict(payload.get("email_status", {}))
        sent = int(status.get("sent", 0))
        failed = int(status.get("failed", 0))
        failed_usernames = list(status.get("failed_usernames", []))
        failed_reasons = dict(status.get("failed_reasons", {}))
        for outcome in outcomes:
            username = outcome["username"]
            if username not in vault:
                continue
            if outcome["ok"]:
                sent += 1
            else:
                failed += 1
                if username not in failed_usernames:
                    failed_usernames.append(username)
                failed_reasons[username] = outcome.get("reason") or "未知错误"
            vault.pop(username, None)
        status.update({
            "sent": sent, "failed": failed, "failed_usernames": failed_usernames,
            "failed_reasons": failed_reasons,
            "completed": sent + failed >= int(status.get("total", 0)),
        })
        payload["password_vault"] = vault
        payload["email_status"] = status
        if status["completed"]:
            payload.pop("email_dispatch", None)
        else:
            payload["email_dispatch"] = dispatch
        run.payload = payload
        run.save(update_fields=["payload"])
        return bool(dispatch.get("pending")) and not status["completed"]


def recover_expired_password_email_batch(run_id: int) -> bool:
    """将租约超时的条目放回 pending，供 Beat 触发的恢复任务重投。"""
    with transaction.atomic():
        run = UserSyncRun.objects.select_for_update().filter(id=run_id).first()
        if not run:
            return False
        payload = dict(run.payload or {})
        dispatch = dict(payload.get("email_dispatch", {}))
        pending = list(dispatch.get("pending", []))
        inflight = []
        recovered = []
        now = timezone.now()
        for item in dispatch.get("inflight", []):
            expires_at = parse_datetime(str(item.get("lease_expires_at") or ""))
            if expires_at and expires_at <= now:
                recovered.append({"user_id": item["user_id"], "username": item["username"]})
            else:
                inflight.append(item)
        if not recovered:
            return False
        pending.extend(recovered)
        dispatch.update({"pending": pending, "inflight": inflight})
        payload["email_dispatch"] = dispatch
        run.payload = payload
        run.save(update_fields=["payload"])
        return True


def complete_password_email_delivery(run_id: int, username: str, ok: bool, reason: str = "") -> dict:
    """回写单封邮件结果并清理对应加密密码。"""
    try:
        with transaction.atomic():
            run = UserSyncRun.objects.select_for_update().filter(id=run_id).first()
            if not run:
                return {"result": False, "message": f"run {run_id} not found"}

            payload = dict(run.payload or {})
            vault = dict(payload.get("password_vault", {}))
            if username not in vault:
                return {"result": True, "data": {"ignored": True}}
            email_status = dict(payload.get("email_status", {}))

            sent = int(email_status.get("sent", 0))
            failed = int(email_status.get("failed", 0))
            failed_usernames = list(email_status.get("failed_usernames", []))
            failed_reasons = dict(email_status.get("failed_reasons", {}))

            if ok:
                sent += 1
            else:
                failed += 1
                if username not in failed_usernames:
                    failed_usernames.append(username)
                failed_reasons[username] = reason or "未知错误"

            total = int(email_status.get("total", 0))
            completed = (sent + failed) >= total

            email_status.update({
                "sent": sent,
                "failed": failed,
                "failed_usernames": failed_usernames,
                "failed_reasons": failed_reasons,
                "completed": completed,
            })
            vault.pop(username, None)
            payload["password_vault"] = vault
            payload["email_status"] = email_status
            run.payload = payload
            run.save(update_fields=["payload"])
            return {
                "result": True,
                "data": {"sent": sent, "failed": failed, "completed": completed},
            }
    except Exception as e:
        logger.error(
            f"update_email_status 失败 run_id={run_id} username={username}: {e}",
            exc_info=True,
        )
        return {"result": False, "message": str(e)}
