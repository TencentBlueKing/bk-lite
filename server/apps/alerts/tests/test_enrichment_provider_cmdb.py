from unittest.mock import patch, MagicMock
from apps.alerts.enrichment.keys import build_binding_key
from apps.alerts.enrichment.providers.cmdb import CMDBProvider


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_groups_by_model_and_batches_ids(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {
        "1": {"owner": "alice"}, "2": {"owner": "bob"},
    }
    k1 = build_binding_key({"model_id": "host", "_id": "1"})
    k2 = build_binding_key({"model_id": "host", "_id": "2"})
    out = CMDBProvider().fetch_batch([k1, k2], {"_authorized_team_ids": [7]})
    assert inst.search_instances_batch.call_count == 1
    inst.search_instances_batch.assert_called_once_with(
        model_id="host", ids=["1", "2"], organization_ids=[7]
    )
    assert out[k1] == [{"owner": "alice"}]
    assert out[k2] == [{"owner": "bob"}]


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_miss_returns_empty_list(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {}
    k = build_binding_key({"model_id": "host", "_id": "9"})
    out = CMDBProvider().fetch_batch([k], {"_authorized_team_ids": [7]})
    assert out[k] == []
