"""management 命令 + services/role_manage + utils/db_utils 单元测试。

调用真实 management 命令（call_command），断言真实 DB 副作用；
只在涉及外部缓存时 mock permission_cache。
"""
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.system_mgmt.models import App, CustomMenuGroup, Group, LoginModule, Menu, Role, SystemSettings, User
from apps.system_mgmt.services.role_manage import RoleManage

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# create_user 命令
# ---------------------------------------------------------------------------
def test_create_user_basic():
    out = StringIO()
    # 必须显式传 email：不传时 argparse 置 None，EmailField 非空约束会失败
    call_command("create_user", "newuser", "secret123", "--email", "newuser@x.com", stdout=out)
    user = User.objects.get(username="newuser")
    # 密码已被 hash
    assert user.password != "secret123"
    assert user.display_name == "newuser"
    # Default 组被加入 group_list
    default_group = Group.objects.get(name="Default", parent_id=0)
    assert default_group.id in user.group_list
    assert "成功创建用户" in out.getvalue()


def test_create_user_superuser_assigns_admin_role():
    out = StringIO()
    call_command(
        "create_user", "boss", "pw", "--email", "boss@x.com", "--display_name", "Boss", "--is_superuser", stdout=out
    )
    user = User.objects.get(username="boss")
    assert user.email == "boss@x.com"
    assert user.display_name == "Boss"
    admin_role = Role.objects.get(name="admin", app="")
    assert admin_role.id in user.role_list


def test_create_user_already_exists():
    User.objects.create(username="dup", password="x", display_name="dup", email="d@x.com")
    out = StringIO()
    call_command("create_user", "dup", "pw", stdout=out)
    assert "已存在" in out.getvalue()
    # 不应创建第二个
    assert User.objects.filter(username="dup").count() == 1


# ---------------------------------------------------------------------------
# clean_group_data 命令
# ---------------------------------------------------------------------------
def test_clean_group_creates_default_when_missing():
    # 确保 id=1 不存在
    Group.objects.filter(id=1).delete()
    User.objects.create(username="g1u", password="x", display_name="u", email="u@x.com", group_list=[])
    out = StringIO()
    with patch("apps.system_mgmt.management.commands.clean_group_data.clear_users_permission_cache"):
        call_command("clean_group_data", stdout=out)
    g = Group.objects.get(id=1)
    assert g.name == "Default" and g.parent_id == 0
    # 所有用户 group_list 被设为 [1]
    assert User.objects.get(username="g1u").group_list == [1]


def test_clean_group_noop_when_correct():
    Group.objects.filter(id=1).delete()
    Group.objects.create(id=1, name="Default", parent_id=0)
    out = StringIO()
    call_command("clean_group_data", stdout=out)
    assert "默认组数据正确" in out.getvalue()


def test_clean_group_migrates_wrong_id1():
    Group.objects.filter(id=1).delete()
    # id=1 是个错误的组（非 Default）
    Group.objects.create(id=1, name="WrongOne", parent_id=0, description="d")
    u = User.objects.create(username="mig", password="x", display_name="u", email="m@x.com", group_list=[1])
    out = StringIO()
    call_command("clean_group_data", stdout=out)
    # id=1 现在应是 Default
    assert Group.objects.get(id=1).name == "Default"
    # 旧组被迁移到新 id，仍存在
    assert Group.objects.filter(name="WrongOne").exists()
    new_id = Group.objects.get(name="WrongOne").id
    u.refresh_from_db()
    assert 1 not in u.group_list
    assert new_id in u.group_list


# ---------------------------------------------------------------------------
# init_login_settings 命令
# ---------------------------------------------------------------------------
def test_init_login_settings_creates_module_and_settings():
    LoginModule.objects.filter(source_type="wechat").delete()
    call_command("init_login_settings")
    assert LoginModule.objects.filter(source_type="wechat", is_build_in=True).exists()
    assert SystemSettings.objects.filter(key="login_expired_time").exists()
    assert SystemSettings.objects.filter(key="enable_otp").exists()
    assert SystemSettings.objects.filter(key="watermark_text").exists()


def test_init_login_settings_idempotent():
    call_command("init_login_settings")
    call_command("init_login_settings")
    assert LoginModule.objects.filter(source_type="wechat", is_build_in=True).count() == 1


# ---------------------------------------------------------------------------
# init_custom_menu 命令
# ---------------------------------------------------------------------------
def test_init_custom_menu_creates_groups_for_builtin_apps():
    app = App.objects.create(name="myapp", display_name="My App", url="/m", is_build_in=True)
    CustomMenuGroup.objects.filter(app="myapp").delete()
    out = StringIO()
    call_command("init_custom_menu", stdout=out)
    grp = CustomMenuGroup.objects.get(app="myapp", display_name="默认菜单")
    assert grp.is_build_in is True
    assert grp.is_enabled is True
    assert app.display_name in grp.description


# ---------------------------------------------------------------------------
# init_bk_login_settings 命令
# ---------------------------------------------------------------------------
def test_init_bk_login_settings_creates_bk_module():
    Role.objects.get_or_create(app="opspilot", name="normal")
    LoginModule.objects.filter(source_type="bk_login").delete()
    call_command("init_bk_login_settings")
    lm = LoginModule.objects.get(source_type="bk_login", name="蓝鲸平台")
    assert lm.is_build_in is True
    assert lm.other_config["app_id"] == "weops_saas"
    assert lm.enabled is False


# ---------------------------------------------------------------------------
# RoleManage 服务
# ---------------------------------------------------------------------------
def _make_menus():
    Menu.objects.create(name="host-view", display_name="主机-查看-x", order=1, app="cmdb", menu_type="资产")
    Menu.objects.create(name="host-edit", display_name="主机-编辑-x", order=2, app="cmdb", menu_type="资产")
    Menu.objects.create(name="alarm", display_name="告警-x", order=3, app="cmdb", menu_type="监控")


def test_role_manage_superuser_gets_all_menus():
    _make_menus()
    rm = RoleManage()
    result = rm.get_all_menus("cmdb", user_menus=None, is_superuser=True)
    # 两个 type 分组
    type_names = {r["name"] for r in result}
    assert type_names == {"资产", "监控"}
    asset = next(r for r in result if r["name"] == "资产")
    host = next(c for c in asset["children"] if c["name"] == "host")
    assert set(host["operation"]) == {"view", "edit"}
    # display_name = "-".join(split("-")[:-1]) -> "主机-查看-x" 去掉末段 "x" 并以空格连接
    assert host["display_name"] == "主机 查看"


def test_role_manage_non_superuser_no_menus_returns_empty():
    _make_menus()
    rm = RoleManage()
    result = rm.get_all_menus("cmdb", user_menus=[], is_superuser=False)
    assert result == []


def test_role_manage_filters_by_user_menus():
    _make_menus()
    rm = RoleManage()
    result = rm.get_all_menus("cmdb", user_menus=["host-view"], is_superuser=False)
    # 仅保留 host-view
    asset = next(r for r in result if r["name"] == "资产")
    host = next(c for c in asset["children"] if c["name"] == "host")
    assert host["operation"] == ["view"]
    # 没有监控分组（alarm 被过滤）
    assert all(r["name"] != "监控" for r in result)


def test_role_manage_transform_empty():
    assert RoleManage.transform_data([]) == []


# ---------------------------------------------------------------------------
# db_utils.SQLExecute
# ---------------------------------------------------------------------------
def test_sql_execute_returns_dict_rows(monkeypatch):
    from django.db import connection

    from apps.system_mgmt.utils.db_utils import SQLExecute

    # SQLExecute 用 os.getenv("DB_NAME") 新建连接；指向当前测试库
    monkeypatch.setenv("DB_NAME", connection.settings_dict["NAME"])

    # SQLExecute 走独立连接，看不到当前测试事务里未提交的数据，
    # 因此查询 migration 已提交的 systemsettings 表，验证返回 dict 行结构。
    rows = SQLExecute.execute_sql(
        "SELECT key, value FROM system_mgmt_systemsettings LIMIT 1", []
    )
    assert isinstance(rows, list)
    if rows:
        assert "key" in rows[0] and "value" in rows[0]


def test_sql_execute_error_returns_empty_list(monkeypatch):
    from django.db import connection

    from apps.system_mgmt.utils.db_utils import SQLExecute

    monkeypatch.setenv("DB_NAME", connection.settings_dict["NAME"])
    # 非法 SQL -> 异常被捕获，返回 []
    rows = SQLExecute.execute_sql("SELECT * FROM not_a_real_table_xyz", [])
    assert rows == []
