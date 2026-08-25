from unittest.mock import MagicMock, patch

import pytest

from apps.cmdb.services.instance import InstanceManage


def _mock_graph(return_instances):
    ctx = MagicMock()
    ctx.__enter__.return_value.query_entity.return_value = (return_instances, len(return_instances))
    return ctx


@patch("apps.cmdb.services.instance.GraphClient")
def test_search_inst_batch_by_ids(mock_gc):
    uuid_1 = "123e4567-e89b-42d3-a456-426614174001"
    uuid_2 = "123e4567-e89b-42d3-a456-426614174002"
    mock_gc.return_value = _mock_graph(
        [
            {"inst_uuid": uuid_1, "inst_name": "h1", "owner": "alice"},
            {"inst_uuid": uuid_2, "inst_name": "h2", "owner": "bob"},
        ]
    )
    result = InstanceManage.search_inst_batch(model_id="host", inst_uuids=[uuid_1, uuid_2])
    assert result[uuid_1]["owner"] == "alice"
    assert result[uuid_2]["owner"] == "bob"
    args, _ = mock_gc.return_value.__enter__.return_value.query_entity.call_args
    params = args[1]
    assert any(p.get("field") == "inst_uuid" and p.get("type") == "str[]" for p in params)


@patch("apps.cmdb.services.instance.GraphClient")
def test_search_inst_batch_empty_returns_empty(mock_gc):
    assert InstanceManage.search_inst_batch(model_id="host", inst_uuids=[]) == {}
    mock_gc.assert_not_called()


@patch("apps.cmdb.services.instance.GraphClient")
def test_search_inst_batch_rejects_numeric_ids(mock_gc):
    with pytest.raises(Exception, match="inst_uuid/inst_uuids"):
        InstanceManage.search_inst_batch(model_id="host", ids=[1, 2])
    mock_gc.assert_not_called()
