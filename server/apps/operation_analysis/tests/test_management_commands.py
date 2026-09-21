"""运营分析管理命令的覆盖测试。

对照 specs/capabilities/legacy-prd-运营分析-管理.md：内置命名空间/数据源/默认组织的初始化。
"""

import logging
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
    # 命名空间不可用时，画布、数据源与标签作为一个声明式集合回滚。
    assert not DataSourceTag.objects.exists()
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
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    assert DataSourceTag.objects.exists()
    assert DataSourceAPIModel.objects.exists()
    assert all(source.groups == [] for source in DataSourceAPIModel.objects.filter(is_build_in=True))


_RETIRE_SUMMARY_TEMPLATE = "[SourceApiInit] 已下架内置场景数据源 %s 个"
_RETIRE_ITEM_TEMPLATE = "[SourceApiInit] 下架内置数据源：%s"
_RETIRED_LAYOUT_KEY = "CMDB 3D机房布局::cmdb/get_room3d_layout"
_RETIRED_ROOMS_KEY = "CMDB 机房列表::cmdb/get_room_list"
_CUSTOM_DATASOURCE_SENTINEL = "custom-room3d-ds-sentinel"


def _retire_log_records(caplog, template):
    return [record for record in caplog.records if record.name == "operation_analysis" and record.msg == template]


@pytest.mark.django_db
def test_init_source_api_data_retires_room3d_builtin_datasources(settings, caplog):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    leftover_layout = DataSourceAPIModel.objects.create(
        name="CMDB 3D机房布局",
        rest_api="cmdb/get_room3d_layout",
        chart_type=["room3D"],
        is_build_in=True,
        is_active=True,
        build_in_key=_RETIRED_LAYOUT_KEY,
        created_by="system",
        updated_by="system",
    )
    leftover_rooms = DataSourceAPIModel.objects.create(
        name="CMDB 机房列表（选项）",
        rest_api="cmdb/get_room_list",
        chart_type=[],
        is_build_in=True,
        is_active=True,
        build_in_key=_RETIRED_ROOMS_KEY,
        created_by="system",
        updated_by="system",
    )
    custom = DataSourceAPIModel.objects.create(
        name=f"我的机房布局-{_CUSTOM_DATASOURCE_SENTINEL}",
        rest_api="cmdb/get_room3d_layout",
        chart_type=["room3D"],
        is_build_in=False,
        is_active=True,
        created_by="alice",
        updated_by="alice",
    )

    with caplog.at_level(logging.DEBUG, logger="operation_analysis"):
        call_command("init_source_api_data")

    leftover_layout.refresh_from_db()
    leftover_rooms.refresh_from_db()
    custom.refresh_from_db()
    assert leftover_layout.chart_type == []
    assert leftover_layout.is_active is False
    assert leftover_rooms.is_active is False
    assert custom.chart_type == ["room3D"]
    assert custom.is_active is True
    assert custom.name == f"我的机房布局-{_CUSTOM_DATASOURCE_SENTINEL}"
    assert not DataSourceAPIModel.objects.filter(name="CMDB 3D机房布局", chart_type=["room3D"]).exists()

    summary_records = _retire_log_records(caplog, _RETIRE_SUMMARY_TEMPLATE)
    assert len(summary_records) == 1
    summary = summary_records[0]
    assert summary.levelno == logging.INFO
    assert summary.args == (2,)
    assert summary.getMessage() == "[SourceApiInit] 已下架内置场景数据源 2 个"
    formatted_summary = logging.Formatter().format(summary)
    assert "[SourceApiInit] 已下架内置场景数据源 2 个" in formatted_summary
    assert _CUSTOM_DATASOURCE_SENTINEL not in summary.getMessage()
    assert _CUSTOM_DATASOURCE_SENTINEL not in formatted_summary
    assert _CUSTOM_DATASOURCE_SENTINEL not in str(summary.args)

    item_records = _retire_log_records(caplog, _RETIRE_ITEM_TEMPLATE)
    assert len(item_records) == 2
    assert {record.levelno for record in item_records} == {logging.DEBUG}
    assert {record.args for record in item_records} == {
        (_RETIRED_LAYOUT_KEY,),
        (_RETIRED_ROOMS_KEY,),
    }
    assert {record.getMessage() for record in item_records} == {
        f"[SourceApiInit] 下架内置数据源：{_RETIRED_LAYOUT_KEY}",
        f"[SourceApiInit] 下架内置数据源：{_RETIRED_ROOMS_KEY}",
    }
    for record in item_records:
        formatted = logging.Formatter().format(record)
        assert record.getMessage() in formatted
        assert _CUSTOM_DATASOURCE_SENTINEL not in record.getMessage()
        assert _CUSTOM_DATASOURCE_SENTINEL not in formatted
        assert _CUSTOM_DATASOURCE_SENTINEL not in str(record.args)

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="operation_analysis"):
        call_command("init_source_api_data")
    leftover_layout.refresh_from_db()
    leftover_rooms.refresh_from_db()
    custom.refresh_from_db()
    assert leftover_layout.is_active is False
    assert leftover_rooms.is_active is False
    assert custom.is_active is True
    assert not _retire_log_records(caplog, _RETIRE_SUMMARY_TEMPLATE)
    assert not _retire_log_records(caplog, _RETIRE_ITEM_TEMPLATE)


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
    import importlib

    return importlib.import_module("apps.operation_analysis.migrations.0019_set_cloud_cost_distribution_field_schema")


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
    cloud_source = DataSourceAPIModel.objects.get(rest_api="cmdb/get_cloud_resource_cost_distribution")
    legacy_params = cloud_source.params
    group_by = next(param for param in legacy_params if param["name"] == "group_by")
    group_by["alias_name"] = "旧别名"
    cloud_source.params = legacy_params
    cloud_source.save(update_fields=["params"])

    # 强制更新模式再次运行 → 覆盖 force_update 分支，不应新增
    call_command("init_source_api_data", "--force-update")
    assert DataSourceAPIModel.objects.count() == count_before
    cloud_source.refresh_from_db()
    group_by = next(param for param in cloud_source.params if param["name"] == "group_by")
    assert group_by["alias_name"] == "分组维度"


@pytest.mark.django_db
def test_init_source_api_data_force_update_reclaims_legacy_identity_regardless_of_creator(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    legacy = DataSourceAPIModel.objects.create(
        name="今日告警状态总览",
        rest_api="alert/get_alert_today_status_summary",
        desc="曾由管理员编辑的旧内置数据源",
        created_by="admin",
        updated_by="admin",
    )

    call_command("init_source_api_data", "--force-update")

    legacy.refresh_from_db()
    assert legacy.is_build_in is True
    assert legacy.build_in_key == "今日告警状态总览::alert/get_alert_today_status_summary"
    assert legacy.name == "今日产生关闭与当前处理中"
    assert legacy.updated_by == "system"
    assert legacy.desc != "曾由管理员编辑的旧内置数据源"


@pytest.mark.django_db
def test_init_source_api_data_force_update_does_not_claim_custom_same_rest_api_only(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    custom = DataSourceAPIModel.objects.create(
        name="我的今日告警总览",
        rest_api="alert/get_alert_today_status_summary",
        desc="用户自定义同接口数据源",
        created_by="user",
        updated_by="user",
    )

    call_command("init_source_api_data", "--force-update")

    custom.refresh_from_db()
    assert custom.is_build_in is False
    assert custom.build_in_key in (None, "")
    assert custom.name == "我的今日告警总览"
    builtin = DataSourceAPIModel.objects.get(build_in_key="今日告警状态总览::alert/get_alert_today_status_summary")
    assert builtin.pk != custom.pk
    assert builtin.name == "今日产生关闭与当前处理中"


@pytest.mark.django_db
def test_init_source_api_data_keeps_empty_groups_on_existing_builtin(settings):
    from apps.system_mgmt.models.user import Group

    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    Group.objects.get_or_create(name="Default")
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(name="今日产生关闭与当前处理中")
    source.groups = []
    source.save(update_fields=["groups"])

    call_command("init_source_api_data", "--force-update")

    source.refresh_from_db()
    assert source.groups == []


@pytest.mark.django_db
def test_init_source_api_data_keeps_existing_non_empty_groups(settings):
    from apps.system_mgmt.models.user import Group

    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    Group.objects.get_or_create(name="Default")
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(name="今日产生关闭与当前处理中")
    source.groups = [99]
    source.save(update_fields=["groups"])

    call_command("init_source_api_data", "--force-update")

    source.refresh_from_db()
    assert source.groups == [99]


# --------------------------------------------------------------------------
# init_default_groups
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_init_default_groups_skips_builtin_datasource():
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default", parent_id=0)
    builtin = DataSourceAPIModel.objects.create(
        name="keep-empty",
        rest_api="keep/empty",
        groups=[],
        is_build_in=True,
        build_in_key="keep-empty",
    )
    custom = DataSourceAPIModel.objects.create(
        name="fill-custom",
        rest_api="fill/custom",
        groups=[],
        is_build_in=False,
    )
    call_command("init_default_groups")
    builtin.refresh_from_db()
    custom.refresh_from_db()
    assert builtin.groups == []
    assert custom.groups  # 自定义空名单仍补 Default


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
    directory = Directory.objects.create(
        name="网络拓扑测试目录",
        groups=[root_default.id],
        created_by="system",
    )

    for object_type, meta in CANVAS_TYPE_REGISTRY.items():
        extra = {}
        if object_type == "networkTopology":
            extra = {"directory": directory, "base_url": "https://weops.example.com"}
        empty = meta.model.objects.create(
            name=f"无组织-{object_type}",
            groups=[],
            created_by="system",
            **extra,
        )
        existing = meta.model.objects.create(
            name=f"已分组-{object_type}",
            groups=[99],
            created_by="system",
            **extra,
        )
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
