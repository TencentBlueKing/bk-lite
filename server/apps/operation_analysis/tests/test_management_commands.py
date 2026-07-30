"""运营分析管理命令的覆盖测试。

对照 specs/capabilities/legacy-prd-运营分析-管理.md：内置命名空间/数据源/默认组织的初始化。
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.models.models import Directory
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY

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
    settings.NATS_SERVERS = "tls://user:pwd%40value@example.com:4222"
    call_command("init_default_namespace")

    ns = NameSpace.objects.get(name="默认命名空间")
    assert ns.account == "user"
    assert ns.decrypt_password == "pwd@value"
    assert ns.enable_tls is True
    assert ns.domain == "example.com:4222"


@pytest.mark.django_db
@pytest.mark.parametrize("nats_servers", ["myhost:4222", "nats://myhost:4222"])
def test_init_default_namespace_plain_host_uses_explicit_nats_options(settings, nats_servers):
    settings.NATS_SERVERS = nats_servers
    settings.NATS_OPTIONS = {
        "user": "configured-user",
        "password": "configured-password",
    }
    call_command("init_default_namespace")

    ns = NameSpace.objects.get(name="默认命名空间")
    assert ns.domain == "myhost:4222"
    assert ns.account == "configured-user"
    assert ns.decrypt_password == "configured-password"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nats_servers",
    [
        "",
        "not-a-valid-url",
        "http://user:secret@nats.internal:4222",
        "nats://nats.internal:4222",
        "nats://user@nats.internal:4222",
        "nats://user:secret@nats.internal",
        "nats://user:secret@[bad:4222",
        "nats://user:secret@bad host:4222",
        "nats://user:secret@bad%20host:4222",
        "nats://user:secret@bad%00host:4222",
        "nats://user:secret@nats.internal:0",
        "user:secret@nats.internal:4222",
        "nats://%20:secret@nats.internal:4222",
        "nats://user:%20@nats.internal:4222",
        "nats://:@nats.internal:4222",
    ],
)
def test_init_default_namespace_rejects_invalid_config_without_writing(settings, monkeypatch, nats_servers):
    settings.NATS_SERVERS = nats_servers
    settings.NATS_OPTIONS = {}
    monkeypatch.delenv("NATS_SERVERS", raising=False)

    with pytest.raises(CommandError, match="NATS_SERVERS"):
        call_command("init_default_namespace")

    assert not NameSpace.objects.filter(name="默认命名空间").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nats_options",
    [
        {"user": "configured-user"},
        {"password": "configured-password"},
        {"token": "configured-token"},
        {"user": " ", "password": "configured-password"},
        {"user": "configured-user", "password": " "},
    ],
)
def test_init_default_namespace_rejects_incomplete_nats_options_without_writing(settings, nats_options):
    settings.NATS_SERVERS = "myhost:4222"
    settings.NATS_OPTIONS = nats_options

    with pytest.raises(CommandError, match="NATS_SERVERS"):
        call_command("init_default_namespace")

    assert not NameSpace.objects.filter(name="默认命名空间").exists()


@pytest.mark.django_db
def test_batch_init_warns_and_continues_when_default_namespace_config_is_invalid(settings):
    from apps.system_mgmt.models.user import Group

    Group.objects.create(name="Default", parent_id=0)
    settings.NATS_SERVERS = "nats://user:secret@[bad:4222"
    settings.NATS_OPTIONS = {}
    output = StringIO()

    call_command("batch_init", apps="operation_analysis", stdout=output)

    assert not NameSpace.objects.filter(name="默认命名空间").exists()
    assert "默认命名空间初始化跳过（CommandError）" in output.getvalue()
    assert "NATS_SERVERS 配置非法" in output.getvalue()
    assert "批量初始化完成" in output.getvalue()
    assert DataSourceTag.objects.exists()
    assert not DataSourceAPIModel.objects.exists()

    settings.NATS_SERVERS = "nats.internal:4222"
    settings.NATS_OPTIONS = {
        "user": "configured-user",
        "password": "configured-password",
    }
    recovered_output = StringIO()
    call_command("batch_init", apps="operation_analysis", stdout=recovered_output)

    assert NameSpace.objects.filter(name="默认命名空间").exists()
    assert DataSourceAPIModel.objects.exists()
    assert "批量初始化完成" in recovered_output.getvalue()


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
def test_init_default_namespace_rotates_legacy_credentials_without_breaking_datasource_relation(settings):
    namespace = NameSpace.objects.create(
        name="默认命名空间",
        account="admin",
        password="nats_password",
        domain="legacy-nats:4222",
    )
    source = DataSourceAPIModel.objects.create(
        name="存量 NATS 数据源",
        rest_api="legacy/get_data",
        source_type=DataSourceAPIModel.SOURCE_TYPE_NATS,
    )
    source.namespaces.add(namespace)
    original_id = namespace.id
    settings.NATS_SERVERS = "new-nats:4222"
    settings.NATS_OPTIONS = {
        "user": "rotated-user",
        "password": "rotated-password",
    }

    call_command("init_default_namespace")

    namespace.refresh_from_db()
    assert namespace.id == original_id
    assert namespace.account == "rotated-user"
    assert namespace.decrypt_password == "rotated-password"
    assert namespace.domain == "new-nats:4222"
    assert source.namespaces.filter(id=original_id).exists()


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
    from apps.system_mgmt.models.user import Group

    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    default_group, _ = Group.objects.get_or_create(name="Default")
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    assert DataSourceTag.objects.exists()
    assert DataSourceAPIModel.objects.exists()
    assert DataSourceAPIModel.objects.filter(groups=[default_group.id]).exists()


@pytest.mark.django_db
def test_init_source_api_data_creates_room3d_datasource(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(name="CMDB 3D机房布局", rest_api="cmdb/get_room3d_layout")

    assert source.chart_type == ["room3D"]
    server_room_param = source.params[0]
    assert {key: server_room_param[key] for key in ("name", "type", "value", "alias_name", "filterType")} == {
        "name": "server_room_id",
        "type": "string",
        "value": "",
        "alias_name": "机房ID",
        "filterType": "params",
    }
    assert list(source.tag.values_list("tag_id", flat=True)) == ["cmdb"]


@pytest.mark.django_db
def test_init_source_api_data_creates_cloud_cost_distribution_contract(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(rest_api="cmdb/get_cloud_resource_cost_distribution")
    params = {item["name"]: item for item in source.params}
    fields = {item["key"]: item for item in source.field_schema}

    assert source.chart_type == ["topN"]
    assert params["group_by"] == {
        "name": "group_by",
        "type": "string",
        "value": "instance_type",
        "alias_name": "排行主体",
        "filterType": "params",
    }
    assert "options" not in params["group_by"]
    assert fields["key"]["value_type"] == "string"
    assert fields["total_cost"]["value_type"] == "number"
    assert fields["instance_count"]["value_type"] == "number"
    assert fields["pct"]["value_type"] == "number"


class _MigrationTarget:
    def __init__(self, params, field_schema):
        self.params = params
        self.field_schema = field_schema
        self.save_calls = []

    def save(self, *, update_fields):
        self.save_calls.append(tuple(update_fields))


class _MigrationQuerySet:
    def __init__(self, target):
        self.target = target

    def first(self):
        return self.target


class _MigrationManager:
    def __init__(self, target, expected_rest_api):
        self.target = target
        self.expected_rest_api = expected_rest_api

    def filter(self, **kwargs):
        assert kwargs == {"rest_api": self.expected_rest_api}
        return _MigrationQuerySet(self.target)


class _MigrationApps:
    def __init__(self, target, expected_rest_api):
        self.model = type(
            "FakeDataSourceAPIModel",
            (),
            {"objects": _MigrationManager(target, expected_rest_api)},
        )

    def get_model(self, app_label, model_name):
        assert (app_label, model_name) == (
            "operation_analysis",
            "DataSourceAPIModel",
        )
        return self.model


def _distribution_migration():
    pytest.skip("0018_set_cloud_cost_distribution_field_schema 已不在当前迁移链中")


def test_cloud_cost_distribution_migration_updates_existing_group_by_and_is_idempotent():
    migration = _distribution_migration()
    target = _MigrationTarget(
        params=[
            {
                "name": "department",
                "type": "string",
                "value": "研发部",
                "filterType": "filter",
            },
            {
                "name": "group_by",
                "type": "number",
                "value": "legacy",
                "alias_name": "旧排行字段",
                "filterType": "params",
                "options": ["instance_type", "department", "user"],
                "legacy_note": "保留",
            },
        ],
        field_schema=[],
    )
    apps = _MigrationApps(target, migration._TARGET_REST_API)

    migration._set_distribution_field_schema(apps, schema_editor=None)

    assert target.params == [
        {
            "name": "department",
            "type": "string",
            "value": "研发部",
            "filterType": "filter",
        },
        {
            "name": "group_by",
            "type": "string",
            "value": "instance_type",
            "alias_name": "排行主体",
            "filterType": "params",
            "legacy_note": "保留",
        },
    ]
    assert target.field_schema == migration._DISTRIBUTION_FIELD_SCHEMA
    assert target.save_calls == [("params", "field_schema", "updated_at")]

    migration._set_distribution_field_schema(apps, schema_editor=None)

    assert target.save_calls == [("params", "field_schema", "updated_at")]


def test_cloud_cost_distribution_migration_appends_missing_group_by_and_preserves_other_params():
    migration = _distribution_migration()
    existing_param = {
        "name": "billing_period",
        "type": "timeRange",
        "value": "",
        "alias_name": "计费日期",
        "filterType": "filter",
        "options": ["不应被迁移删除"],
    }
    target = _MigrationTarget(params=[existing_param], field_schema=None)
    apps = _MigrationApps(target, migration._TARGET_REST_API)

    migration._set_distribution_field_schema(apps, schema_editor=None)

    assert target.params == [
        existing_param,
        {
            "name": "group_by",
            "alias_name": "排行主体",
            "type": "string",
            "value": "instance_type",
            "filterType": "params",
        },
    ]
    assert target.field_schema == migration._DISTRIBUTION_FIELD_SCHEMA
    assert target.save_calls == [("params", "field_schema", "updated_at")]


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


@pytest.mark.django_db
def test_init_source_api_data_backfills_empty_groups_on_existing_sources(settings):
    from apps.system_mgmt.models.user import Group

    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    default_group, _ = Group.objects.get_or_create(name="Default")
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(name="今日告警状态总览")
    source.groups = []
    source.save(update_fields=["groups"])

    call_command("init_source_api_data", "--force-update")

    source.refresh_from_db()
    assert source.groups == [default_group.id]


@pytest.mark.django_db
def test_init_source_api_data_keeps_existing_non_empty_groups(settings):
    from apps.system_mgmt.models.user import Group

    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    Group.objects.get_or_create(name="Default")
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(name="今日告警状态总览")
    source.groups = [99]
    source.save(update_fields=["groups"])

    call_command("init_source_api_data", "--force-update")

    source.refresh_from_db()
    assert source.groups == [99]


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
def test_init_default_groups_covers_all_registered_canvas_models():
    from apps.system_mgmt.models.user import Group

    root_default, _ = Group.objects.get_or_create(name="Default", parent_id=0)
    records = []

    for object_type, meta in CANVAS_TYPE_REGISTRY.items():
        required_fields = {}
        if object_type == "networkTopology":
            directory = Directory.objects.create(name="网络拓扑目录", groups=[], created_by="system")
            required_fields = {"directory": directory, "base_url": "https://weops.example.com"}
        empty = meta.model.objects.create(name=f"无组织-{object_type}", groups=[], created_by="system", **required_fields)
        existing = meta.model.objects.create(name=f"已分组-{object_type}", groups=[99], created_by="system", **required_fields)
        records.append((empty, existing))

    call_command("init_default_groups")

    for empty, existing in records:
        empty.refresh_from_db()
        existing.refresh_from_db()
        assert empty.groups == [root_default.id]
        assert existing.groups == [99]


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
