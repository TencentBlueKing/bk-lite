import inspect
from unittest.mock import MagicMock

from apps.cmdb.constants.constants import MODEL, MODEL_ASSOCIATION
from apps.cmdb.services import auto_relation_reconcile, unique_rule
from apps.cmdb.services.model_graph_query import (
    model_association_info_search,
    model_association_search,
    parse_attrs,
    search_model_info,
)


def test_parse_attrs_unescapes_quotes():
    assert parse_attrs('[{"attr_id": \\"ip\\"}]') == [{"attr_id": "ip"}]


def test_unique_rule_and_auto_relation_no_longer_import_model_manage():
    unique_src = inspect.getsource(unique_rule)
    reconcile_src = inspect.getsource(auto_relation_reconcile)
    assert "from apps.cmdb.services.model import ModelManage" not in unique_src
    assert "from apps.cmdb.services.model import ModelManage" not in reconcile_src


def test_search_model_info_returns_first_match(monkeypatch):
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.query_entity.return_value = ([{"model_id": "host", "_id": 1}], 1)
    monkeypatch.setattr("apps.cmdb.services.model_graph_query.GraphClient", lambda: fake)

    assert search_model_info("host") == {"model_id": "host", "_id": 1}
    fake.query_entity.assert_called_once_with(MODEL, [{"field": "model_id", "type": "str=", "value": "host"}])


def test_search_model_info_returns_empty_when_missing(monkeypatch):
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.query_entity.return_value = ([], 0)
    monkeypatch.setattr("apps.cmdb.services.model_graph_query.GraphClient", lambda: fake)

    assert search_model_info("missing") == {}


def test_model_association_info_search_returns_first_edge(monkeypatch):
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.query_edge.return_value = [{"model_asst_id": "host_belong_biz"}]
    monkeypatch.setattr("apps.cmdb.services.model_graph_query.GraphClient", lambda: fake)

    assert model_association_info_search("host_belong_biz") == {"model_asst_id": "host_belong_biz"}
    fake.query_edge.assert_called_once_with(
        MODEL_ASSOCIATION,
        [{"field": "model_asst_id", "type": "str=", "value": "host_belong_biz"}],
    )


def test_model_association_search_uses_or_query(monkeypatch):
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.query_edge.return_value = [{"src_model_id": "host"}]
    monkeypatch.setattr("apps.cmdb.services.model_graph_query.GraphClient", lambda: fake)

    assert model_association_search("host") == [{"src_model_id": "host"}]
    fake.query_edge.assert_called_once_with(
        MODEL_ASSOCIATION,
        [
            {"field": "src_model_id", "type": "str=", "value": "host"},
            {"field": "dst_model_id", "type": "str=", "value": "host"},
        ],
        param_type="OR",
    )
