from unittest.mock import MagicMock, patch

from apps.alerts.enrichment.keys import build_binding_key
from apps.alerts.enrichment.providers.cmdb import CMDBProvider

U1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
U2 = "c28e467a-501d-426f-a3c3-6e560c7b33cb"


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_groups_by_model_and_batches_uuids(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {
        U1: {"owner": "alice"},
        U2: {"owner": "bob"},
    }
    k1 = build_binding_key({"model_id": "host", "inst_uuid": U1})
    k2 = build_binding_key({"model_id": "host", "inst_uuid": U2})
    out = CMDBProvider().fetch_batch([k1, k2], {"_authorized_team_ids": [7]})
    assert inst.search_instances_batch.call_count == 1
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1, U2],
            "organization_ids": [7],
        },
        _timeout=3,
    )
    assert out[k1] == [{"owner": "alice"}]
    assert out[k2] == [{"owner": "bob"}]


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_maps_monitor_object_name_to_cmdb_model(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"ip_addr": "10.11.27.147"}}
    key = build_binding_key({"model_id": "Host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [1]})

    assert out[key] == [{"ip_addr": "10.11.27.147"}]
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1],
            "organization_ids": [1],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_miss_returns_empty_list(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {}
    k = build_binding_key({"model_id": "host", "inst_uuid": U1})
    out = CMDBProvider().fetch_batch([k], {"_authorized_team_ids": [7]})
    assert out[k] == []


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_marks_failed_keys_instead_of_real_miss(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = TimeoutError("rpc timeout")
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert result.records[key] == []
    assert result.failed_keys == {key}
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1],
            "organization_ids": [7],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_uses_cmdb_uuid_without_model_and_stops(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"owner": "alice"}}
    key = build_binding_key({"inst_uuid": U1, "monitor_id": "0001"})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert out[key] == [{"owner": "alice"}]
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "inst_uuids": [U1],
            "organization_ids": [7],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_falls_back_to_monitor_id_when_uuid_misses(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst

    def search(*, params, _timeout):
        if "inst_uuids" in params:
            return {}
        assert params["monitor_ids"] == ["0001"]
        assert "model_id" not in params
        return {"0001": {"owner": "ops"}}

    inst.search_instances_batch.side_effect = search
    key = build_binding_key({"inst_uuid": U1, "monitor_id": "0001"})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert out[key] == [{"owner": "ops"}]
    assert inst.search_instances_batch.call_count == 2


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_uuid_failure_does_not_query_monitor_id(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = TimeoutError("rpc timeout")
    key = build_binding_key({"inst_uuid": U1, "monitor_id": "0001"})

    result = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert result.failed_keys == {key}
    inst.search_instances_batch.assert_called_once()


@patch("apps.alerts.enrichment.providers.cmdb.monotonic", return_value=10.0)
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_does_not_start_group_after_deadline(mock_cmdb_cls, _mock_clock):
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_deadline_at": 9.0},
    )

    assert result.failed_keys == {key}
    assert result.budget_exhausted_keys == {key}
    mock_cmdb_cls.return_value.search_instances_batch.assert_not_called()
