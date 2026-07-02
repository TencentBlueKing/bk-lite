"""运营分析管理命令的覆盖测试。

对照 spec/prd/运营分析·管理：内置命名空间/数据源/默认组织的初始化。
"""

import pytest
from django.core.management import call_command

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.models.models import Directory

# --------------------------------------------------------------------------
# init_default_namespace
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_init_default_namespace_creates_from_nats_url(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")

    ns = NameSpace.objects.get(name="默认命名空间")
    assert ns.account == "admin"
    assert ns.domain == "127.0.0.1:4222"
    assert ns.enable_tls is False


@pytest.mark.django_db
def test_init_default_namespace_creates_from_tls_url(settings):
    settings.NATS_SERVERS = "tls://user:pwd@example.com:4222"
    call_command("init_default_namespace")

    ns = NameSpace.objects.get(name="默认命名空间")
    assert ns.enable_tls is True
    assert ns.domain == "example.com:4222"


@pytest.mark.django_db
def test_init_default_namespace_plain_host(settings):
    settings.NATS_SERVERS = "myhost:4222"
    call_command("init_default_namespace")

    ns = NameSpace.objects.get(name="默认命名空间")
    assert ns.domain == "myhost:4222"
    assert ns.account == "admin"


@pytest.mark.django_db
def test_init_default_namespace_no_servers_returns_early(settings):
    settings.NATS_SERVERS = ""
    import os

    old = os.environ.pop("NATS_SERVERS", None)
    try:
        call_command("init_default_namespace")
        assert not NameSpace.objects.filter(name="默认命名空间").exists()
    finally:
        if old is not None:
            os.environ["NATS_SERVERS"] = old


@pytest.mark.django_db
def test_init_default_namespace_rerun_updates_changed_config(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    # 第二次使用不同账号/域名 → 走更新分支
    settings.NATS_SERVERS = "nats://other:newpwd@10.0.0.1:4222"
    call_command("init_default_namespace")

    ns = NameSpace.objects.get(name="默认命名空间")
    assert ns.account == "other"
    assert ns.domain == "10.0.0.1:4222"


@pytest.mark.django_db
def test_init_default_namespace_rerun_no_change(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    # 完全相同配置再次执行 → 走"未变化"分支
    call_command("init_default_namespace")

    assert NameSpace.objects.filter(name="默认命名空间").count() == 1


# --------------------------------------------------------------------------
# init_source_api_data
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_init_source_api_data_creates_tags_and_sources(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    assert DataSourceTag.objects.exists()
    assert DataSourceAPIModel.objects.exists()


@pytest.mark.django_db
def test_init_source_api_data_without_namespace_aborts():
    # 无默认命名空间 → 标签会创建，但数据源初始化提前返回
    call_command("init_source_api_data")
    assert not DataSourceAPIModel.objects.exists()


@pytest.mark.django_db
def test_init_source_api_data_force_update_is_idempotent(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    call_command("init_source_api_data")
    count_before = DataSourceAPIModel.objects.count()
    # 强制更新模式再次运行 → 覆盖 force_update 分支，不应新增
    call_command("init_source_api_data", "--force-update")
    assert DataSourceAPIModel.objects.count() == count_before


# --------------------------------------------------------------------------
# init_default_groups
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_init_default_groups_fills_empty_groups():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    obj = Directory.objects.create(name="无组织目录", groups=[], created_by="system")
    skip = Directory.objects.create(name="有组织目录", groups=[5], created_by="system")

    call_command("init_default_groups")

    obj.refresh_from_db()
    skip.refresh_from_db()
    assert obj.groups  # 已补充默认组织
    assert skip.groups == [5]  # 非空保持不变


@pytest.mark.django_db
def test_init_default_groups_uses_root_default_group_when_child_has_same_name():
    from apps.system_mgmt.models.user import Group

    root_default, _ = Group.objects.get_or_create(name="Default", parent_id=0)
    parent = Group.objects.create(name="业务组织", parent_id=0)
    Group.objects.create(name="Default", parent_id=parent.id)
    obj = Directory.objects.create(name="无组织目录", groups=[], created_by="system")

    call_command("init_default_groups")

    obj.refresh_from_db()
    assert obj.groups == [root_default.id]


@pytest.mark.django_db
def test_init_default_groups_without_default_group_returns_early():
    # 没有名为 Default 的组织 → 捕获异常并提前返回，不抛出
    from apps.system_mgmt.models.user import Group

    Group.objects.filter(name="Default").delete()
    call_command("init_default_groups")
    assert True


# --------------------------------------------------------------------------
# load_json_data
# --------------------------------------------------------------------------


def test_load_support_json_missing_file_raises():
    from apps.operation_analysis.common.load_json_data import load_support_json

    with pytest.raises(FileNotFoundError):
        load_support_json("__not_exists__.json")


def test_load_support_json_reads_existing_file():
    from apps.operation_analysis.common.load_json_data import load_support_json

    data = load_support_json("namespace.json")
    assert isinstance(data, list)
    assert data[0]["name"] == "默认命名空间"
