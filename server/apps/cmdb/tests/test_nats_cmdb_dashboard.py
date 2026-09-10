import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.nats import nats as N


@pytest.mark.parametrize(
    ("locale", "classification_name", "model_name"),
    [
        ("zh-Hans", "硬件设备", "物理服务器"),
        ("en", "Hardware Device", "Physical Server"),
    ],
)
def test_cmdb_model_instance_top_uses_request_locale(
    monkeypatch,
    locale,
    classification_name,
    model_name,
):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {})
    monkeypatch.setattr(
        N.ClassificationManage,
        "search_model_classification",
        lambda language: [
            {
                "classification_id": "harware",
                "classification_name": classification_name if language == locale else "wrong language",
            }
        ],
    )
    monkeypatch.setattr(
        N.ModelManage,
        "search_model",
        lambda language, permissions_map: [
            {
                "model_id": "physical_server",
                "model_name": model_name if language == locale else "wrong language",
                "classification_id": "harware",
            }
        ],
    )
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"physical_server": 63})

    result = N.get_cmdb_model_instance_top(
        limit=5,
        user_info={"locale": locale},
    )

    assert result == {
        "result": True,
        "data": [
            {
                "model": model_name,
                "model_id": "physical_server",
                "classification": classification_name,
                "classification_id": "harware",
                "count": 63,
            }
        ],
        "message": "",
    }


@pytest.mark.parametrize(
    ("locale", "classification_name", "model_name"),
    [
        ("zh-Hans", "硬件设备", "物理服务器"),
        ("en", "Hardware Device", "Physical Server"),
    ],
)
def test_model_inst_statistics_uses_request_locale(
    monkeypatch,
    locale,
    classification_name,
    model_name,
):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {})
    monkeypatch.setattr(
        N.ClassificationManage,
        "search_model_classification",
        lambda language: [
            {
                "classification_id": "harware",
                "classification_name": classification_name if language == locale else "wrong language",
            }
        ],
    )
    monkeypatch.setattr(
        N.ModelManage,
        "search_model",
        lambda language, permissions_map: [
            {
                "model_id": "physical_server",
                "model_name": model_name if language == locale else "wrong language",
                "classification_id": "harware",
            }
        ],
    )
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"physical_server": 63})

    result = N.get_model_inst_statistics(user_info={"locale": locale})

    assert result == {
        "result": True,
        "data": [
            {
                "classification": classification_name,
                "model": model_name,
                "model_id": "physical_server",
                "count": 63,
            }
        ],
        "message": "",
    }


def test_cmdb_model_instance_top_defaults_to_model_group_by(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {})
    monkeypatch.setattr(
        N.ClassificationManage,
        "search_model_classification",
        lambda language: [
            {"classification_id": "hardware", "classification_name": "硬件设备"},
            {"classification_id": "software", "classification_name": "软件"},
        ],
    )
    monkeypatch.setattr(
        N.ModelManage,
        "search_model",
        lambda language, permissions_map: [
            {"model_id": "physical_server", "model_name": "物理服务器", "classification_id": "hardware"},
            {"model_id": "vm", "model_name": "虚拟机", "classification_id": "hardware"},
            {"model_id": "app", "model_name": "应用", "classification_id": "software"},
        ],
    )
    monkeypatch.setattr(
        N.InstanceManage,
        "model_inst_count",
        lambda permissions_map: {"physical_server": 10, "vm": 5, "app": 20},
    )

    default_result = N.get_cmdb_model_instance_top(limit=10, user_info={"locale": "zh-Hans"})
    grouped = N.get_cmdb_model_instance_top(limit=10, group_by="classification", user_info={"locale": "zh-Hans"})

    assert [item["model_id"] for item in default_result["data"]] == ["app", "physical_server", "vm"]
    assert grouped["data"] == [
        {"classification": "软件", "classification_id": "software", "count": 20},
        {"classification": "硬件设备", "classification_id": "hardware", "count": 15},
    ]


@pytest.mark.django_db
def test_cmdb_statistics_collect_coverage_counts_unique_task_instances(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N.ClassificationManage, "search_model_classification", lambda: [])
    monkeypatch.setattr(N.ModelManage, "search_model", lambda permissions_map: [])
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"host": 4})
    monkeypatch.setattr(N, "_authorized_collect_instance_keys", lambda keys, permissions_map, creator="": set(keys))
    CollectModels.objects.create(
        name="cover-a",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"inst_uuid": "u1"}, {"_id": "2"}, {"inst_uuid": "u1"}],
    )
    CollectModels.objects.create(
        name="cover-b",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"inst_uuid": "u3"}],
    )
    CollectModels.objects.create(
        name="other-org",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[9],
        instances=[{"inst_uuid": "u9"}],
    )
    CollectModels.objects.create(
        name="system-hidden",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[1],
        is_system=True,
        instances=[{"inst_uuid": "sys"}],
    )

    result = N.get_cmdb_statistics(user_info={"team": 1, "user": "alice"})

    assert result["result"] is True
    assert result["data"]["instance_count"] == 4
    assert result["data"]["collected_instance_count"] == 3
    assert result["data"]["collect_coverage_rate"] == 75.0


def test_authorized_collect_instance_keys_queries_graph_batches_and_intersects(fake_graph):
    """图查询路径：按 uuid/id 分批查，并与任务钥匙求交（图未返回的视为无权/已删）。"""
    permission_map = {"1": {"inst_names": []}}
    expected_format = N.InstanceManage._build_format_permission_dict(permission_map, "")

    def query_entity(label, params, format_permission_dict=None, **kwargs):
        assert label == N.INSTANCE
        assert format_permission_dict == expected_format
        field = params[0]["field"]
        if field == "inst_uuid":
            assert set(params[0]["value"]) == {"u1", "gone", "u3"}
            # 图只回有权且仍存在的实例；gone 不回
            return ([{"inst_uuid": "u1"}, {"inst_uuid": "u3", "_id": 99}], 2)
        if field == "id":
            assert params[0]["value"] == [2]
            # 数字钥匙无权：空结果
            return ([], 0)
        raise AssertionError(f"unexpected params: {params}")

    fake_graph("apps.cmdb.nats.nats", query_entity=query_entity)

    keys = N._authorized_collect_instance_keys({"u1", "2", "gone", "u3"}, permission_map)

    assert keys == {"u1", "u3"}


def test_authorized_collect_instance_keys_collapses_uuid_and_numeric_id_aliases(fake_graph):
    """同一实例同时以 uuid 与数字 id 出现在任务里时，只计一次。"""

    def query_entity(label, params, format_permission_dict=None, **kwargs):
        entity = {"inst_uuid": "u1", "_id": 99, "id": 99}
        field = params[0]["field"]
        if field == "inst_uuid":
            assert set(params[0]["value"]) == {"u1"}
            return ([entity], 1)
        if field == "id":
            assert params[0]["value"] == [99]
            return ([entity], 1)
        raise AssertionError(f"unexpected params: {params}")

    fake_graph("apps.cmdb.nats.nats", query_entity=query_entity)

    keys = N._authorized_collect_instance_keys({"u1", "99"}, {})

    assert keys == {"u1"}


@pytest.mark.django_db
def test_cmdb_statistics_collect_coverage_intersects_authorized_instances(monkeypatch, fake_graph):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {"1": {"inst_names": []}})
    monkeypatch.setattr(N.ClassificationManage, "search_model_classification", lambda: [])
    monkeypatch.setattr(N.ModelManage, "search_model", lambda permissions_map: [])
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"host": 4})

    def query_entity(label, params, format_permission_dict=None, **kwargs):
        field = params[0]["field"]
        if field == "inst_uuid":
            return ([{"inst_uuid": "u1"}, {"inst_uuid": "u3"}], 2)
        if field == "id":
            return ([], 0)
        return ([], 0)

    fg = fake_graph("apps.cmdb.nats.nats", query_entity=query_entity)
    CollectModels.objects.create(
        name="cover-mix",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"inst_uuid": "u1"}, {"_id": "2"}, {"inst_uuid": "gone"}, {"inst_uuid": "u3"}],
    )

    result = N.get_cmdb_statistics(user_info={"team": 1, "user": "alice"})

    assert result["result"] is True
    assert result["data"]["collected_instance_count"] == 2
    assert result["data"]["collect_coverage_rate"] == 50.0
    assert any(call[0] == "query_entity" for call in fg.calls)


@pytest.mark.django_db
def test_cmdb_statistics_collect_coverage_counts_dual_key_instance_once(monkeypatch, fake_graph):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {"1": {"inst_names": []}})
    monkeypatch.setattr(N.ClassificationManage, "search_model_classification", lambda: [])
    monkeypatch.setattr(N.ModelManage, "search_model", lambda permissions_map: [])
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"host": 2})

    def query_entity(label, params, format_permission_dict=None, **kwargs):
        entity = {"inst_uuid": "u1", "_id": 99}
        field = params[0]["field"]
        if field in {"inst_uuid", "id"}:
            return ([entity], 1)
        return ([], 0)

    fake_graph("apps.cmdb.nats.nats", query_entity=query_entity)
    CollectModels.objects.create(
        name="cover-dual",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"inst_uuid": "u1"}, {"_id": "99"}],
    )

    result = N.get_cmdb_statistics(user_info={"team": 1, "user": "alice"})

    assert result["result"] is True
    assert result["data"]["instance_count"] == 2
    assert result["data"]["collected_instance_count"] == 1
    assert result["data"]["collect_coverage_rate"] == 50.0
