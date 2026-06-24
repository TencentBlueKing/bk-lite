"""apps/system_mgmt/tasks.py 单元测试。

只 mock 真实外部边界（RpcClient、send_email_to_user、permission_cache、self.retry），
断言真实 DB 副作用与返回结构。
"""
import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone as django_timezone

from apps.system_mgmt.models import Channel, ErrorLog, Group, LoginModule, SystemSettings, User
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt import tasks

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# write_error_log_async
# ---------------------------------------------------------------------------
def test_write_error_log_async_success():
    result = tasks.write_error_log_async.run(
        username="alice",
        app="cmdb",
        module="host",
        error_message="boom",
        domain="domain.com",
        stack_trace="trace...",
    )
    assert result == {"result": True, "message": "Error log written successfully"}
    log = ErrorLog.objects.get(username="alice")
    assert log.app == "cmdb"
    assert log.error_message == "boom"
    assert log.stack_trace == "trace..."


def test_write_error_log_async_retry_exhausted():
    """create 抛错时走 retry 分支，最终 MaxRetriesExceeded 返回失败。"""
    with patch.object(ErrorLog.objects, "create", side_effect=RuntimeError("db down")):
        task = tasks.write_error_log_async
        # 模拟 self.retry 抛出 MaxRetriesExceededError
        with patch.object(task, "retry", side_effect=task.MaxRetriesExceededError()):
            result = task.run(
                username="bob",
                app="a",
                module="m",
                error_message="e",
                domain="d",
                stack_trace="s",
            )
    assert result == {"result": False, "message": "Failed to write error log after retries"}


# ---------------------------------------------------------------------------
# sync_user_and_group_by_login_module
# ---------------------------------------------------------------------------
def test_sync_by_login_module_not_found():
    result = tasks.sync_user_and_group_by_login_module(999999)
    assert result == {"result": False, "message": "Login module not found or not enabled."}


def test_sync_by_login_module_disabled():
    lm = LoginModule.objects.create(name="ldap1", source_type="ldap", enabled=False, other_config={})
    result = tasks.sync_user_and_group_by_login_module(lm.id)
    assert result == {"result": False, "message": "Login module not found or not enabled."}


def test_sync_by_login_module_calls_rpc_and_syncs():
    lm = LoginModule.objects.create(
        name="ldap2",
        source_type="ldap",
       
        enabled=True,
        other_config={"namespace": "ns1", "root_group": "ROOT", "domain": "corp.com", "default_roles": [1]},
    )
    rpc_data = {
        "result": True,
        "message": "",
        "data": {
            "user_list": [{"username": "u1", "display_name": "User One", "email": "u1@x.com", "departments": ["g1"]}],
            "group_list": [{"id": "g1", "parent_id": None, "name": "Dept1"}],
        },
    }
    fake_client = MagicMock()
    fake_client.request.return_value = rpc_data
    with patch("apps.system_mgmt.tasks.RpcClient", return_value=fake_client), patch(
        "apps.system_mgmt.tasks.clear_users_permission_cache"
    ):
        tasks.sync_user_and_group_by_login_module(lm.id)
    fake_client.request.assert_called_once_with("sync_data")
    # 验证 DB 副作用
    assert Group.objects.filter(name="ROOT", parent_id=0).exists()
    assert Group.objects.filter(name="Dept1").exists()
    assert User.objects.filter(username="u1", domain="corp.com").exists()


# ---------------------------------------------------------------------------
# sync_user_and_groups (orchestrator)
# ---------------------------------------------------------------------------
def _make_login_module(**cfg):
    return LoginModule.objects.create(
        name="mod",
        source_type="ldap",
       
        enabled=True,
        other_config=cfg,
    )


def test_sync_user_and_groups_creates_and_returns_counts():
    lm = _make_login_module(root_group="R", domain="d1.com", default_roles=[2])
    user_list = [
        {"username": "a", "display_name": "A", "email": "a@d.com", "departments": ["e1"]},
        {"username": "b", "display_name": "B", "email": "b@d.com", "departments": []},
    ]
    group_list = [{"id": "e1", "parent_id": None, "name": "G1"}]
    with patch("apps.system_mgmt.tasks.clear_users_permission_cache"):
        result = tasks.sync_user_and_groups(user_list, group_list, lm)
    assert result["result"] is True
    assert result["data"]["synced_users"] == 2
    assert result["data"]["synced_groups"] == 1
    a = User.objects.get(username="a", domain="d1.com")
    # 部门 e1 映射到本地 group
    g1 = Group.objects.get(name="G1")
    assert a.group_list == [g1.id]
    assert a.role_list == [2]


def test_sync_user_and_groups_handles_exception():
    lm = _make_login_module(root_group="R", domain="d.com")
    # group_list 缺少 name -> KeyError 触发 except 分支
    bad_group_list = [{"id": "x", "parent_id": None}]
    result = tasks.sync_user_and_groups([], bad_group_list, lm)
    assert result["result"] is False
    assert "message" in result


# ---------------------------------------------------------------------------
# _sync_groups: 更新名称 / 复用同名组 / 删除多余组
# ---------------------------------------------------------------------------
def test_sync_groups_updates_name_when_changed():
    lm = _make_login_module(root_group="ROOT", domain="d.com")
    parent, _ = Group.objects.get_or_create(name="ROOT", parent_id=0, defaults={"description": "x"})
    # 已存在带 external_id 的子组，名称将被更新
    existing = Group.objects.create(name="OldName", parent_id=parent.id, external_id="ext1", description="d")
    group_list = [{"id": "ext1", "parent_id": None, "name": "NewName"}]
    mapping = tasks._sync_groups(group_list, parent, None)
    existing.refresh_from_db()
    assert existing.name == "NewName"
    assert mapping["ext1"] == existing.id


def test_sync_groups_adopts_existing_by_name():
    lm = _make_login_module(root_group="ROOT", domain="d.com")
    parent, _ = Group.objects.get_or_create(name="ROOT", parent_id=0, defaults={"description": "x"})
    # 同名但没有 external_id 的组，应被认领并写入 external_id
    existing = Group.objects.create(name="SameName", parent_id=parent.id, external_id=None, description="d")
    group_list = [{"id": "extZ", "parent_id": None, "name": "SameName"}]
    mapping = tasks._sync_groups(group_list, parent, None)
    existing.refresh_from_db()
    assert existing.external_id == "extZ"
    assert mapping["extZ"] == existing.id


def test_sync_groups_deletes_stale_external_groups():
    lm = _make_login_module(root_group="ROOT", domain="d.com")
    parent, _ = Group.objects.get_or_create(name="ROOT", parent_id=0, defaults={"description": "x"})
    stale = Group.objects.create(name="Stale", parent_id=parent.id, external_id="goneext", description="d")
    # 新的 group_list 不含 goneext -> 应被删除
    group_list = [{"id": "keep", "parent_id": None, "name": "Keep"}]
    tasks._sync_groups(group_list, parent, None)
    assert not Group.objects.filter(id=stale.id).exists()
    assert Group.objects.filter(name="Keep", parent_id=parent.id).exists()


def test_sync_groups_recurses_into_children():
    lm = _make_login_module(root_group="ROOT", domain="d.com")
    parent, _ = Group.objects.get_or_create(name="ROOT", parent_id=0, defaults={"description": "x"})
    group_list = [
        {"id": "p1", "parent_id": None, "name": "Parent1"},
        {"id": "c1", "parent_id": "p1", "name": "Child1"},
    ]
    mapping = tasks._sync_groups(group_list, parent, None)
    assert "p1" in mapping and "c1" in mapping
    child = Group.objects.get(name="Child1")
    p1 = Group.objects.get(name="Parent1")
    assert child.parent_id == p1.id


# ---------------------------------------------------------------------------
# _update_group_hierarchy
# ---------------------------------------------------------------------------
def test_update_group_hierarchy_reparents():
    g_parent = Group.objects.create(name="HP", parent_id=0, description="d")
    g_child = Group.objects.create(name="HC", parent_id=0, description="d")
    group_list = [
        {"id": "pp", "parent_id": None, "name": "HP"},
        {"id": "cc", "parent_id": "pp", "name": "HC"},
    ]
    external_to_name = {"pp": "HP", "cc": "HC"}
    tasks._update_group_hierarchy(group_list, external_to_name)
    g_child.refresh_from_db()
    assert g_child.parent_id == g_parent.id


def test_update_group_hierarchy_skips_missing_group():
    group_list = [{"id": "x", "parent_id": "y", "name": "NoSuch"}]
    external_to_name = {"y": "AlsoNoSuch"}
    # 不应抛异常（DoesNotExist 被捕获）
    tasks._update_group_hierarchy(group_list, external_to_name)


def test_update_group_hierarchy_skips_no_parent():
    group_list = [{"id": "x", "parent_id": None, "name": "n"}]
    tasks._update_group_hierarchy(group_list, {})  # parent_id 不在 mapping -> continue


# ---------------------------------------------------------------------------
# _sync_users: 创建 + 更新
# ---------------------------------------------------------------------------
def test_sync_users_creates_and_updates():
    g = Group.objects.create(name="UG", parent_id=0, description="d")
    mapping = {"deptA": g.id}
    # 先存在一个用户用于更新
    User.objects.create(username="exist", display_name="Old", domain="dd.com", group_list=[], role_list=[])
    user_list = [
        {"username": "exist", "display_name": "NewName", "departments": ["deptA"]},
        {"username": "fresh", "display_name": "Fresh", "email": "f@x.com", "departments": ["deptA"]},
    ]
    with patch("apps.system_mgmt.tasks.clear_users_permission_cache") as m_clear:
        result = tasks._sync_users(user_list, mapping, "dd.com", [9])
    assert set(result) == {"exist@dd.com", "fresh@dd.com"}
    exist = User.objects.get(username="exist", domain="dd.com")
    assert exist.display_name == "NewName"
    assert exist.group_list == [g.id]
    fresh = User.objects.get(username="fresh", domain="dd.com")
    assert fresh.role_list == [9]
    assert fresh.group_list == [g.id]
    m_clear.assert_called_once()


# ---------------------------------------------------------------------------
# check_password_expiry_and_notify
# ---------------------------------------------------------------------------
def test_password_expiry_never_expires():
    SystemSettings.objects.update_or_create(key="pwd_set_validity_period", defaults={"value": "0"})
    result = tasks.check_password_expiry_and_notify()
    assert result == {"result": True, "message": "Password never expires, skipping reminder"}


def test_password_expiry_no_email_channel():
    SystemSettings.objects.update_or_create(key="pwd_set_validity_period", defaults={"value": "180"})
    result = tasks.check_password_expiry_and_notify()
    assert result == {"result": False, "message": "No email channel configured"}


def test_password_expiry_notifies_soon_and_already_expired():
    SystemSettings.objects.update_or_create(key="pwd_set_validity_period", defaults={"value": "180"})
    SystemSettings.objects.update_or_create(key="pwd_set_expiry_reminder_days", defaults={"value": "7"})
    channel = Channel.objects.create(name="mail", channel_type=ChannelChoices.EMAIL, config={"smtp_pwd": "p"})

    now = django_timezone.now()
    # 即将过期：last_modified 175 天前 -> 剩余 ~5 天
    User.objects.create(
        username="soon", display_name="Soon", email="soon@x.com", domain="d.com",
        disabled=False, password_last_modified=now - datetime.timedelta(days=175),
    )
    # 已过期：last_modified 200 天前 -> 剩余 < 0
    User.objects.create(
        username="expired", display_name="Exp", email="exp@x.com", domain="d.com",
        disabled=False, password_last_modified=now - datetime.timedelta(days=200),
    )
    # 还很久：last_modified 10 天前 -> 跳过
    User.objects.create(
        username="ok", display_name="Ok", email="ok@x.com", domain="d.com",
        disabled=False, password_last_modified=now - datetime.timedelta(days=10),
    )

    with patch("apps.system_mgmt.tasks.send_email_to_user", return_value={"result": True}) as m_send, \
            patch.object(Channel, "decrypt_field"):
        result = tasks.check_password_expiry_and_notify()

    assert result["result"] is True
    assert result["notified"] == 2
    assert result["failed"] == 0
    # 验证邮件主题区分即将过期 / 已过期
    subjects = {c.kwargs.get("subject", c.args[3] if len(c.args) > 3 else None) for c in m_send.call_args_list}
    assert "密码即将过期提醒" in subjects
    assert "密码已过期提醒" in subjects


def test_password_expiry_send_failure_counts_skipped():
    SystemSettings.objects.update_or_create(key="pwd_set_validity_period", defaults={"value": "180"})
    Channel.objects.create(name="mail", channel_type=ChannelChoices.EMAIL, config={"smtp_pwd": "p"})
    now = django_timezone.now()
    User.objects.create(
        username="fail", display_name="F", email="f@x.com", domain="d.com",
        disabled=False, password_last_modified=now - datetime.timedelta(days=178),
    )
    with patch("apps.system_mgmt.tasks.send_email_to_user", return_value={"result": False, "message": "smtp err"}), \
            patch.object(Channel, "decrypt_field"):
        result = tasks.check_password_expiry_and_notify()
    assert result["result"] is True
    assert result["failed"] == 1
    assert result["notified"] == 0
