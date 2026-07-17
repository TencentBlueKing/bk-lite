"""用户同步-初始密码邮件发送 Celery 任务单测。

覆盖 plan spec 中 #8/#11/#12 项测试场景:
  #8  发送成功 → vault pop 该 username + email_status.sent += 1 + completed 标记
  #11 通道失败重试耗尽 → email_status.failed += 1 + failed_reasons
  #12 vault 解密失败 → 任务失败 + user 不回滚 + email_status.failed_reasons
"""
from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from django.contrib.auth.hashers import make_password

from apps.system_mgmt.models import (
    Group,
    IntegrationInstance,
    User,
    UserSyncRun,
    UserSyncSource,
)
from apps.system_mgmt.tasks import send_initial_password_email, send_initial_password_email_batch
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


@pytest.fixture
def ready_integration_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-sync",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready", "im_notification": "ready"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


@pytest.fixture
def source(ready_integration_instance):
    return UserSyncSource.objects.create(
        name="test-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root",
        business_config={},
        platform_config={"password_init": {"mode": "random", "email_channel_id": 7}},
        field_mapping={},
        schedule_config={},
    )


@pytest.fixture
def group(db):
    return Group.objects.create(name="root", parent_id=0)


@pytest.fixture
def user_with_vault(source, group):
    """已设置临时密码 + vault 加密好 raw 的 user。"""
    raw = "RandomP@ss!2026"
    user = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password=make_password(raw),
        domain="domain.com",
        disabled=False,
        group_list=[group.id],
        sync_source=source,
        temporary_pwd=True,
    )
    run = UserSyncRun.objects.create(
        source=source,
        status="running",
        payload={
            "password_vault": {"alice": encrypt_for_vault(raw)},
            "email_status": {
                "total": 1, "sent": 0, "failed": 0,
                "failed_usernames": [], "failed_reasons": {},
                "completed": False,
            },
        },
    )
    return user, run


@pytest.mark.django_db
def test_success_pops_vault_and_marks_sent(user_with_vault):
    """#8 发送成功 → vault pop + email_status.sent += 1 + completed=True。"""
    user, run = user_with_vault

    with patch(
        "apps.system_mgmt.services.password_init_email.send_email_via_runtime"
    ) as send_email:
        send_email.return_value = {"result": True, "message": "ok"}
        send_initial_password_email.run(user.id, run.id)

    run.refresh_from_db()
    assert "alice" not in (run.payload.get("password_vault") or {})
    assert run.payload["email_status"]["sent"] == 1
    assert run.payload["email_status"]["completed"] is True


@pytest.mark.django_db
def test_initial_password_email_uses_formal_chinese_template(user_with_vault):
    user, _ = user_with_vault

    with patch("apps.system_mgmt.models.Channel.objects.filter") as query:
        query.return_value.first.return_value = object()
        with patch(
            "apps.system_mgmt.utils.channel_utils.send_email",
            return_value={"result": True},
        ) as channel_send_email:
            from apps.system_mgmt.services.password_init_email import send_email_via_runtime

            send_email_via_runtime(user, "RandomP@ss!2026")

    _, kwargs = channel_send_email.call_args
    assert kwargs["title"] == "BK-Lite 账号开通通知"
    assert "账号已由管理员开通" in kwargs["content"]
    assert "用户名" in kwargs["content"]
    assert "RandomP@ss!2026" in kwargs["content"]
    assert "请勿转发、截图或长期保存本邮件" in kwargs["content"]


@pytest.mark.django_db
def test_channel_failure_marks_failed_and_pops_vault(user_with_vault):
    """#11 通道失败 → email_status.failed += 1, vault 仍 pop。"""
    user, run = user_with_vault

    with patch(
        "apps.system_mgmt.services.password_init_email.send_email_via_runtime"
    ) as send_email:
        send_email.return_value = {"result": False, "message": "channel disabled"}
        with patch.object(send_initial_password_email, "retry", side_effect=Retry()):
            with pytest.raises(Retry):
                send_initial_password_email.run(user.id, run.id)

    run.refresh_from_db()
    assert run.payload["email_status"]["failed"] == 0
    assert "alice" in (run.payload.get("password_vault") or {})


@pytest.mark.django_db
def test_complete_delivery_updates_status_and_vault_together(user_with_vault):
    """邮件结果必须在同一事务内累计状态并移除 vault，避免并发任务互相覆盖。"""
    from apps.system_mgmt.nats.email_status import complete_password_email_delivery

    user, run = user_with_vault
    result = complete_password_email_delivery(run.id, user.username, ok=True)

    assert result["result"] is True
    run.refresh_from_db()
    assert run.payload["email_status"]["sent"] == 1
    assert "alice" not in run.payload["password_vault"]


@pytest.mark.django_db
def test_vault_decrypt_failure_user_not_rolled_back(user_with_vault):
    """#12 vault 解密失败 → 任务失败,user.temporary_pwd 不回滚,email_status 标记。"""
    user, run = user_with_vault

    # 把 vault 改成无效密文
    run.payload["password_vault"]["alice"] = "garbage-not-aes-ciphertext"
    run.save(update_fields=["payload"])

    # user 仍是 temporary_pwd=True
    user.refresh_from_db()
    assert user.temporary_pwd is True

    send_initial_password_email.run(user.id, run.id)

    # user 不回滚(账户仍可用,仅邮件缺失)
    user.refresh_from_db()
    assert user.temporary_pwd is True

    run.refresh_from_db()
    assert run.payload["email_status"]["failed"] == 1
    assert run.payload["email_status"]["failed_reasons"]["alice"] == "vault 解密失败"


@pytest.mark.django_db
def test_batch_task_sends_claimed_users_and_updates_status_together(user_with_vault, source, group):
    """批任务在单次 SMTP 调用中发送领取用户，并在结束后一次汇总结果。"""
    alice, run = user_with_vault
    raw_bob = "BobRandomP@ss!2026"
    bob = User.objects.create(
        username="bob",
        display_name="Bob",
        email="bob@example.com",
        password=make_password(raw_bob),
        domain="domain.com",
        disabled=False,
        group_list=[group.id],
        sync_source=source,
        temporary_pwd=True,
    )
    run.payload = {
        "password_vault": {
            "alice": run.payload["password_vault"]["alice"],
            "bob": encrypt_for_vault(raw_bob),
        },
        "email_dispatch": {
            "pending": [
                {"user_id": alice.id, "username": "alice"},
                {"user_id": bob.id, "username": "bob"},
            ],
            "inflight": [],
        },
        "email_status": {
            "total": 2,
            "sent": 0,
            "failed": 0,
            "failed_usernames": [],
            "failed_reasons": {},
            "completed": False,
        },
    }
    run.save(update_fields=["payload"])

    with patch(
        "apps.system_mgmt.services.password_init_email.send_initial_password_emails",
        return_value={"alice": {"result": True}, "bob": {"result": True}},
    ) as send_emails:
        send_initial_password_email_batch.run(run.id)

    deliveries = send_emails.call_args.args[1]
    assert {delivery["username"] for delivery in deliveries} == {"alice", "bob"}
    run.refresh_from_db()
    assert run.payload["email_status"]["sent"] == 2
    assert run.payload["email_status"]["completed"] is True
    assert run.payload["password_vault"] == {}
    assert "email_dispatch" not in run.payload


@pytest.mark.django_db
def test_claim_batch_limits_pending_users_to_200(source):
    """领取操作最多取 200 个用户，剩余用户仍保持待投递。"""
    from apps.system_mgmt.nats.email_status import claim_password_email_batch

    pending = [{"user_id": index, "username": f"user-{index}"} for index in range(201)]
    run = UserSyncRun.objects.create(
        source=source,
        status="running",
        payload={"email_dispatch": {"pending": pending, "inflight": []}},
    )

    claimed = claim_password_email_batch(run.id)

    assert len(claimed) == 200
    run.refresh_from_db()
    assert len(run.payload["email_dispatch"]["pending"]) == 1
    assert len(run.payload["email_dispatch"]["inflight"]) == 200


@pytest.mark.django_db
def test_recover_expired_batch_lease_returns_users_to_pending(source):
    """超时的 inflight 条目会回到 pending，供恢复任务再次投递。"""
    from datetime import timedelta

    from django.utils import timezone

    from apps.system_mgmt.nats.email_status import recover_expired_password_email_batch

    run = UserSyncRun.objects.create(
        source=source,
        status="success",
        payload={
            "email_dispatch": {
                "pending": [],
                "inflight": [{"user_id": 1, "username": "alice", "lease_expires_at": (timezone.now() - timedelta(seconds=1)).isoformat()}],
            },
            "email_status": {"total": 1, "sent": 0, "failed": 0, "completed": False},
        },
    )

    assert recover_expired_password_email_batch(run.id) is True
    run.refresh_from_db()
    assert run.payload["email_dispatch"]["inflight"] == []
    assert run.payload["email_dispatch"]["pending"] == [{"user_id": 1, "username": "alice"}]
