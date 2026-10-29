"""内置数据源 required_app：精确 NATS 目录优先，前缀白名单兜底，外部源保持空。"""

import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer
from apps.operation_analysis.services.datasource_required_app import resolve_or_seed_required_app


def _resolve(rest_api, *, source_type="nats", is_build_in=True):
    return resolve_or_seed_required_app(
        rest_api=rest_api,
        source_type=source_type,
        is_build_in=is_build_in,
    )


def test_unprefixed_builtin_alert_source_maps_to_alarm():
    assert _resolve("get_alert_level_distribution") == "alarm"
    assert _resolve("get_active_alert_top") == "alarm"


def test_alert_prefix_maps_to_alarm_when_catalog_misses():
    assert _resolve("alert/not_a_registered_function") == "alarm"
    assert _resolve("alert/get_alert_trend_data") == "alarm"


def test_cross_module_source_uses_implementing_app_not_name_tokens():
    assert _resolve("monitor/get_cmdb_relation_alert_aggregation") == "monitor"
    # 函数实现在 monitor；即使前缀写成 cmdb，精确目录仍然压过前缀白名单。
    assert _resolve("cmdb/get_cmdb_relation_alert_aggregation") == "monitor"


def test_prefix_whitelist_covers_job_and_system_mgmt_client_names():
    assert _resolve("job/get_job_usage_statistics") == "job"
    assert _resolve("system_mgmt/get_system_usage_statistics") == "system-manager"
    assert _resolve("node/get_node_usage_statistics") == "node"
    assert _resolve("log/log_search") == "log"
    assert _resolve("get_instance_group_by") == "cmdb"


def test_unknown_prefix_and_non_builtin_sources_stay_null():
    assert _resolve("custom/not_in_catalog") is None
    assert _resolve("not_a_registered_function") is None
    assert _resolve("monitor/get_host_resource_top", source_type="mysql") is None
    assert _resolve("elasticsearch-index", source_type="elasticsearch") is None
    assert _resolve("alert/get_alert_trend_data", is_build_in=False) is None
    assert _resolve("get_alert_level_distribution", is_build_in=False) is None


@pytest.mark.django_db
def test_serializer_exposes_required_app_and_rejects_client_writes(authenticated_user):
    datasource = DataSourceAPIModel.objects.create(
        name="alarm-source",
        rest_api="get_alert_level_distribution",
        source_type="nats",
        is_build_in=True,
        required_app="alarm",
        groups=[],
        created_by="system",
        updated_by="system",
    )
    request = APIRequestFactory().get("/operation_analysis/api/data_source/")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    request.user = authenticated_user
    force_authenticate(request, user=authenticated_user)

    payload = DataSourceAPIModelSerializer(datasource, context={"request": request}).data
    assert payload["required_app"] == "alarm"

    writable = DataSourceAPIModelSerializer(
        data={
            "name": "custom",
            "rest_api": "custom/query",
            "source_type": "nats",
            "params": [],
            "chart_type": ["line"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
            "required_app": "alarm",
        },
        context={"request": request},
    )
    assert writable.is_valid(), writable.errors
    assert "required_app" not in writable.validated_data


@pytest.mark.django_db
def test_init_source_api_data_seeds_required_app_without_touching_external_rows(settings, monkeypatch):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    settings.NATS_NAMESPACE = "bklite"
    call_command("init_default_namespace")

    existing = DataSourceAPIModel.objects.create(
        name="告警等级分布",
        rest_api="get_alert_level_distribution",
        source_type="nats",
        is_build_in=True,
        build_in_key="告警等级分布::get_alert_level_distribution",
        required_app=None,
        groups=[],
        created_by="system",
        updated_by="system",
    )
    external = DataSourceAPIModel.objects.create(
        name="外部 ES",
        rest_api="logs-*",
        source_type="elasticsearch",
        is_build_in=False,
        required_app=None,
        groups=[1],
        created_by="alice",
        updated_by="alice",
    )
    custom_nats = DataSourceAPIModel.objects.create(
        name="自定义 NATS",
        rest_api="alert/my_custom_query",
        source_type="nats",
        is_build_in=False,
        required_app=None,
        groups=[1],
        created_by="alice",
        updated_by="alice",
    )

    def fake_load(filename):
        if filename == "tags.json":
            return []
        if filename == "source_api.json":
            return [
                {
                    "name": "告警等级分布",
                    "rest_api": "get_alert_level_distribution",
                    "source_type": "nats",
                    "desc": "",
                    "params": [],
                    "chart_type": ["pie"],
                },
                {
                    "name": "关联告警汇总",
                    "rest_api": "monitor/get_cmdb_relation_alert_aggregation",
                    "source_type": "nats",
                    "desc": "",
                    "params": [],
                    "chart_type": ["single"],
                },
                {
                    "name": "外部表",
                    "rest_api": "",
                    "source_type": "mysql",
                    "desc": "",
                    "params": [],
                    "chart_type": ["table"],
                },
            ]
        raise AssertionError(filename)

    monkeypatch.setattr(
        "apps.operation_analysis.management.commands.init_source_api_data.load_support_json",
        fake_load,
    )
    call_command("init_source_api_data")

    existing.refresh_from_db()
    external.refresh_from_db()
    custom_nats.refresh_from_db()
    relation = DataSourceAPIModel.objects.get(rest_api="monitor/get_cmdb_relation_alert_aggregation")
    mysql = DataSourceAPIModel.objects.get(name="外部表")

    assert existing.required_app == "alarm"
    assert relation.required_app == "monitor"
    assert mysql.required_app is None
    assert external.required_app is None
    assert custom_nats.required_app is None
