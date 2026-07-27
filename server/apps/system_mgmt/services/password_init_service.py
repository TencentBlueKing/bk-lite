"""用户同步-本地密码初始化 service。

对外接口: init_password_for_user(user, mode, business_config, run) -> dict
"""
import secrets

from django.contrib.auth.hashers import make_password
from django.db import transaction

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import UserSyncRun
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.utils.password_vault import decrypt_from_vault, encrypt_for_vault

PASSWORD_INIT_SENTINEL = "UNSET_PASSWORD"
EMAIL_ENQUEUE_ERROR_CODE = "email_enqueue_failed"
# sentinel 完整标记:写进 user.password 字段(非 hash 格式)。
# Django check_password 会先调 is_password_usable 判断是否合法 hash,
# 非合法 hash 直接返回 False → 用户本地永远登录不上。
# reset_password 守卫通过前缀识别。
PASSWORD_INIT_SENTINEL_MARK = f"!{PASSWORD_INIT_SENTINEL}:{PASSWORD_INIT_SENTINEL}"

# Celery 任务顶层引用,便于测试 patch 路径稳定。
from apps.system_mgmt.tasks import send_initial_password_email_batch  # noqa: E402


def _enqueue_email(run) -> None:
    """每个同步运行仅入队一条批量初始密码邮件任务。

    注:必须用 transaction.on_commit 包裹——password_init_service 是在
    user_sync_service._sync_users 的 transaction.atomic() 块内调用,
    vault 写入也是同一 transaction。如果直接 .delay(),Celery worker 立即
    启动查 run.payload.password_vault 拿到的是 atomic 还没 commit 的旧值 → vault 缺。
    on_commit 让任务在 atomic 块成功 commit 后再入队,worker 读到的是最新数据。
    """
    payload = dict(run.payload or {})
    dispatch = dict(payload.get("email_dispatch", {}))
    if dispatch.get("enqueue_status") in ("pending", "enqueued"):
        return
    dispatch["enqueue_status"] = "pending"
    dispatch.pop("enqueue_error", None)
    payload.pop("email_enqueue_error", None)
    payload["email_dispatch"] = dispatch
    run.payload = payload
    run.save(update_fields=["payload"])
    transaction.on_commit(lambda: _publish_password_email_batch(run.id))


def _publish_password_email_batch(run_id: int) -> None:
    """在事务提交后投递任务，并持久化投递结果供同步收尾阶段判断。"""
    try:
        send_initial_password_email_batch.delay(run_id)
    except Exception:
        logger.exception("Initial password email task enqueue failed: run_id=%s", run_id)
        status = "failed"
        # payload 会经同步详情接口返回，不能持久化 broker URL、凭据等原始异常信息。
        error_code = EMAIL_ENQUEUE_ERROR_CODE
    else:
        status = "enqueued"
        error_code = None

    with transaction.atomic():
        run = UserSyncRun.objects.select_for_update().get(pk=run_id)
        payload = dict(run.payload or {})
        dispatch = dict(payload.get("email_dispatch", {}))
        dispatch["enqueue_status"] = status
        dispatch.pop("enqueue_error", None)
        if error_code:
            dispatch["enqueue_error_code"] = error_code
        else:
            dispatch.pop("enqueue_error_code", None)
        payload["email_dispatch"] = dispatch
        payload["email_enqueue_status"] = status
        payload.pop("email_enqueue_error", None)
        if error_code:
            payload["email_enqueue_error_code"] = error_code
        else:
            payload.pop("email_enqueue_error_code", None)
        run.payload = payload
        run.save(update_fields=["payload"])


def _validate_uniform_password(password: str) -> tuple[bool, str]:
    """调 PasswordValidator 校验;True/空字符串 = 通过,False/错误消息 = 不通过。"""
    is_valid, error_message = PasswordValidator.validate_password(password)
    if not is_valid:
        return False, error_message or "密码强度不够"
    return True, ""


def init_password_for_user(user, mode: str, business_config: dict, run) -> dict:
    """
    根据 mode 给同步创建的用户初始化本地密码。
    仅在首次创建时调用,后续同步不再触发。

    Returns:
        dict: {"status": "ok" | "failed",
               "reason": str | None,
               "raw_password": str | None}
    """
    if mode == "none":
        user.password = PASSWORD_INIT_SENTINEL_MARK
        user.temporary_pwd = False
        user.save()
        return {"status": "ok", "reason": None, "raw_password": None}

    if mode == "uniform":
        encrypted_password = (business_config or {}).get("uniform_password", "")
        channel_id = (business_config or {}).get("email_channel_id")
        if not channel_id:
            return {"status": "failed", "reason": "missing_channel", "raw_password": None}
        try:
            raw = decrypt_from_vault(encrypted_password)
        except ValueError:
            return {"status": "failed", "reason": "invalid_uniform_password", "raw_password": None}
        ok, msg = _validate_uniform_password(raw)
        if not ok:
            return {"status": "failed", "reason": "weak_password", "raw_password": None}
        user.password = make_password(raw)
        user.temporary_pwd = True
        user.save()
        _stash_to_vault(run, user.id, user.username, raw)
        _enqueue_email(run)
        return {"status": "ok", "reason": None, "raw_password": raw}

    if mode == "random":
        raw = secrets.token_urlsafe(12)
        channel_id = (business_config or {}).get("email_channel_id")
        if not channel_id:
            return {"status": "failed", "reason": "missing_channel", "raw_password": None}
        user.password = make_password(raw)
        user.temporary_pwd = True
        user.save()
        _stash_to_vault(run, user.id, user.username, raw)
        _enqueue_email(run)
        return {"status": "ok", "reason": None, "raw_password": raw}

    return {"status": "failed", "reason": f"unknown_mode:{mode}", "raw_password": None}


def _stash_to_vault(run, user_id: int, username: str, raw_password: str) -> None:
    """把 raw_password AES 加密后塞进 run.payload.password_vault;初始化 email_status。"""
    payload = dict(run.payload or {})
    vault = dict(payload.get("password_vault", {}))
    vault[username] = encrypt_for_vault(raw_password)
    payload["password_vault"] = vault

    dispatch = dict(payload.get("email_dispatch", {}))
    pending = list(dispatch.get("pending", []))
    if not any(item.get("username") == username for item in pending):
        pending.append({"user_id": user_id, "username": username})
    dispatch["pending"] = pending
    dispatch["inflight"] = list(dispatch.get("inflight", []))
    payload["email_dispatch"] = dispatch

    email_status = dict(payload.get("email_status", {}))
    email_status["total"] = int(email_status.get("total", 0)) + 1
    email_status["sent"] = int(email_status.get("sent", 0))
    email_status["failed"] = int(email_status.get("failed", 0))
    email_status["failed_usernames"] = list(email_status.get("failed_usernames", []))
    email_status["failed_reasons"] = dict(email_status.get("failed_reasons", {}))
    email_status["completed"] = False
    payload["email_status"] = email_status

    run.payload = payload
    run.save(update_fields=["payload"])
