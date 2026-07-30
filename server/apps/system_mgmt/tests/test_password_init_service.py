"""用户同步-本地密码初始化 service 单测。

覆盖 plan spec 中 #1-#7 项测试场景:
  #1 mode=none → sentinel + 无 Celery
  #2 mode=uniform 合规 → 写入密码 + 入队
  #3 mode=uniform 弱密码 → 拒绝
  #4 mode=uniform 缺通道 → 拒绝
  #5 mode=random → 长度 ≥ 12
  #6 mode=random → vault 写入
  #7 mode=random 缺通道 → 拒绝
"""
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import check_password, make_password

from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncRun, UserSyncSource
from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL, PASSWORD_INIT_SENTINEL_MARK, init_password_for_user
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


@pytest.fixture
def ready_integration_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-sync",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


@pytest.fixture
def source(ready_integration_instance):
    return UserSyncSource.objects.create(
        name="test-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root",
        business_config={"password_init": {"mode": "none"}},
        field_mapping={},
        schedule_config={},
    )


@pytest.fixture
def run(source):
    return UserSyncRun.objects.create(
        source=source,
        status="running",
        payload={},
    )


@pytest.fixture
def group(db):
    return Group.objects.create(name="root", parent_id=0)


def _make_user(source, group, username="alice", email="alice@example.com"):
    return User.objects.create(
        username=username,
        display_name=username,
        email=email,
        password=make_password(""),
        domain="domain.com",
        disabled=False,
        group_list=[group.id],
        sync_source=source,
    )


@pytest.mark.django_db
def test_mode_none_uses_sentinel_and_no_celery(source, run, group):
    """#1 mode=none: user.password = sentinel,temporary_pwd=False,不调用 Celery。"""
    user = _make_user(source, group)
    with patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay:
        result = init_password_for_user(user, "none", {}, run)

    user.refresh_from_db()
    assert result["status"] == "ok"
    assert user.password == PASSWORD_INIT_SENTINEL_MARK
    assert check_password("anything", user.password) is False
    assert user.temporary_pwd is False
    delay.assert_not_called()


@pytest.mark.django_db
def test_mode_uniform_success(source, run, group):
    """#2 mode=uniform 合规:密码写入,temporary_pwd=True,入队 Celery 发送邮件。

    service 调 _enqueue_email 用 transaction.on_commit 包裹以避免 race condition。
    测试中 patch 掉 on_commit 让 callback 立即执行(模拟 commit 完成)。
    """
    user = _make_user(source, group)
    cfg = {"uniform_password": encrypt_for_vault("Str0ngP@ss!"), "email_channel_id": 7}
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay:
        result = init_password_for_user(user, "uniform", cfg, run)

    user.refresh_from_db()
    assert result["status"] == "ok"
    assert check_password("Str0ngP@ss!", user.password) is True
    assert user.temporary_pwd is True
    delay.assert_called_once_with(run.id)


@pytest.mark.django_db
def test_mode_uniform_decrypts_persisted_secret(source, run, group):
    """统一密码策略持久化为密文，初始化时仍使用原始密码。"""
    user = _make_user(source, group)
    raw_password = "Str0ngP@ss!"
    cfg = {"uniform_password": encrypt_for_vault(raw_password), "email_channel_id": 7}

    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch("apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"):
        result = init_password_for_user(user, "uniform", cfg, run)

    user.refresh_from_db()
    assert result["status"] == "ok"
    assert check_password(raw_password, user.password) is True


@pytest.mark.django_db
def test_mode_uniform_weak_password_rejected(source, run, group):
    """#3 mode=uniform 弱密码:整批拒绝,user 不变,Celery 不调。"""
    user = _make_user(source, group)
    original_password = user.password
    cfg = {"uniform_password": encrypt_for_vault("123"), "email_channel_id": 7}
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay:
        result = init_password_for_user(user, "uniform", cfg, run)

    assert result["status"] == "failed"
    assert result["reason"] == "weak_password"
    user.refresh_from_db()
    assert user.password == original_password
    delay.assert_not_called()


@pytest.mark.django_db
def test_mode_uniform_missing_channel(source, run, group):
    """#4 mode=uniform 缺 email_channel_id:拒绝。"""
    user = _make_user(source, group)
    cfg = {"uniform_password": "Str0ngP@ss!"}
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay:
        result = init_password_for_user(user, "uniform", cfg, run)

    assert result["status"] == "failed"
    assert result["reason"] == "missing_channel"
    delay.assert_not_called()


@pytest.mark.django_db
def test_mode_random_generates_strong_password(source, run, group):
    """#5 mode=random:密码长度 ≥ 12,temporary_pwd=True,入队 Celery。"""
    user = _make_user(source, group, username="u1")
    cfg = {"email_channel_id": 7}
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay:
        result = init_password_for_user(user, "random", cfg, run)

    assert result["status"] == "ok"
    assert result["raw_password"] is not None
    assert len(result["raw_password"]) >= 12
    user.refresh_from_db()
    assert user.temporary_pwd is True
    delay.assert_called_once_with(run.id)


@pytest.mark.django_db
def test_mode_random_writes_vault(source, run, group):
    """#6 mode=random:run.payload.password_vault 含加密 username,不含明文;email_status 初始化。"""
    user = _make_user(source, group, username="bob")
    raw = "SomeRandomPassword!2026"
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ), patch(
        "apps.system_mgmt.services.password_init_service.secrets.token_urlsafe",
        return_value=raw,
    ):
        init_password_for_user(user, "random", {"email_channel_id": 7}, run)

    run.refresh_from_db()
    vault = run.payload.get("password_vault", {})
    assert "bob" in vault
    assert vault["bob"] != raw
    email_status = run.payload.get("email_status", {})
    assert email_status.get("total") == 1
    assert email_status.get("completed") is False


@pytest.mark.django_db
def test_enqueue_failure_is_persisted_for_sync_finalize(source, run, group):
    """任务代理拒绝时不得把邮件标记为已入队。"""
    user = _make_user(source, group, username="enqueue-failure")
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay",
        side_effect=RuntimeError("amqp://sync-user:broker-secret@broker.example/vhost unavailable"),
    ):
        result = init_password_for_user(user, "random", {"email_channel_id": 7}, run)

    run.refresh_from_db()
    assert result["status"] == "ok"
    assert run.payload["email_dispatch"]["enqueue_status"] == "failed"
    assert run.payload["email_dispatch"]["enqueue_error_code"] == "email_enqueue_failed"
    assert "enqueue_error" not in run.payload["email_dispatch"]
    assert "broker-secret" not in str(run.payload)
    assert run.payload["email_enqueue_status"] == "failed"
    assert run.payload["email_enqueue_error_code"] == "email_enqueue_failed"


@pytest.mark.django_db
def test_multiple_users_enqueue_one_batch_task_without_plaintext_password(source, run, group):
    """同一同步运行只入队一次，待投递信息不包含明文密码。"""
    from apps.system_mgmt.services.password_init_service import init_password_for_user

    alice = _make_user(source, group, username="alice")
    bob = _make_user(source, group, username="bob")
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay, patch(
        "apps.system_mgmt.services.password_init_service.secrets.token_urlsafe",
        side_effect=["AliceP@ss!2026", "BobP@ss!2026"],
    ):
        init_password_for_user(alice, "random", {"email_channel_id": 7}, run)
        init_password_for_user(bob, "random", {"email_channel_id": 7}, run)

    run.refresh_from_db()
    dispatch = run.payload["email_dispatch"]
    assert dispatch["pending"] == [
        {"user_id": alice.id, "username": "alice"},
        {"user_id": bob.id, "username": "bob"},
    ]
    assert "AliceP@ss!2026" not in str(dispatch)
    assert "BobP@ss!2026" not in str(dispatch)
    delay.assert_called_once_with(run.id)


@pytest.mark.django_db
def test_mode_random_missing_channel(source, run, group):
    """#7 mode=random 缺 email_channel_id:拒绝。"""
    user = _make_user(source, group)
    with patch(
        "django.db.transaction.on_commit",
        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    ), patch(
        "apps.system_mgmt.services.password_init_service.send_initial_password_email_batch.delay"
    ) as delay:
        result = init_password_for_user(user, "random", {}, run)

    assert result["status"] == "failed"
    assert result["reason"] == "missing_channel"
    delay.assert_not_called()


@pytest.mark.django_db
def test_sentinel_constants_exist():
    """Sentinel 常量:PASSWORD_INIT_SENTINEL 与 PASSWORD_INIT_SENTINEL_MARK 一致。"""
    assert PASSWORD_INIT_SENTINEL == "UNSET_PASSWORD"
    assert PASSWORD_INIT_SENTINEL_MARK == "!UNSET_PASSWORD:UNSET_PASSWORD"
