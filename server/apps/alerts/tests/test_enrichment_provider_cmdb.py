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
    )
    assert out[k1] == [{"owner": "alice"}]
    assert out[k2] == [{"owner": "bob"}]


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_miss_returns_empty_list(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {}
    k = build_binding_key({"model_id": "host", "inst_uuid": U1})
    out = CMDBProvider().fetch_batch([k], {"_authorized_team_ids": [7]})
    assert out[k] == []
