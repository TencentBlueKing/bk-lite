from unittest.mock import patch, MagicMock
from apps.cmdb.services.instance import InstanceManage


def _mock_graph(return_instances):
    ctx = MagicMock()
    ctx.__enter__.return_value.query_entity.return_value = (return_instances, len(return_instances))
    return ctx


@patch("apps.cmdb.services.instance.GraphClient")
def test_search_inst_batch_by_ids(mock_gc):
    mock_gc.return_value = _mock_graph([
        {"_id": 1, "inst_name": "h1", "owner": "alice"},
        {"_id": 2, "inst_name": "h2", "owner": "bob"},
    ])
    result = InstanceManage.search_inst_batch(model_id="host", ids=[1, 2])
    assert result["1"]["owner"] == "alice"
    assert result["2"]["owner"] == "bob"
    args, _ = mock_gc.return_value.__enter__.return_value.query_entity.call_args
    params = args[1]
    assert any(p.get("type") == "id[]" for p in params)


@patch("apps.cmdb.services.instance.GraphClient")
def test_search_inst_batch_empty_returns_empty(mock_gc):
    assert InstanceManage.search_inst_batch(model_id="host", ids=[]) == {}
    mock_gc.assert_not_called()
