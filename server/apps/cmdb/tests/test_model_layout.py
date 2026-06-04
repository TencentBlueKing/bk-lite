"""Tests for model/classification visibility and layout features."""

import pytest
from unittest.mock import MagicMock

from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.model import ModelManage


@pytest.fixture
def fake_graph(monkeypatch):
    """Mock GraphClient used inside services."""
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    monkeypatch.setattr(
        "apps.cmdb.services.model.GraphClient", lambda: fake
    )
    monkeypatch.setattr(
        "apps.cmdb.services.classification.GraphClient", lambda: fake
    )
    return fake


class TestSearchModelVisibility:
    def _models(self):
        return [
            {"model_id": "host", "model_name": "Host",
             "classification_id": "infra", "group": ["default"],
             "order_id": 1, "is_visible": True},
            {"model_id": "switch", "model_name": "Switch",
             "classification_id": "infra", "group": ["default"],
             "order_id": 0, "is_visible": False},
            {"model_id": "legacy", "model_name": "Legacy",
             "classification_id": "infra", "group": ["default"]},
        ]

    def test_default_filters_hidden_and_backfills(self, fake_graph):
        fake_graph.query_entity.return_value = (self._models(), 3)
        result = ModelManage.search_model(language="en")
        ids = [m["model_id"] for m in result]
        assert "switch" not in ids
        assert set(ids) == {"host", "legacy"}
        legacy = next(m for m in result if m["model_id"] == "legacy")
        assert legacy["order_id"] == 0
        assert all(m["is_visible"] is True for m in result)

    def test_include_hidden_returns_all_with_flag(self, fake_graph):
        fake_graph.query_entity.return_value = (self._models(), 3)
        result = ModelManage.search_model(language="en", include_hidden=True)
        ids = [m["model_id"] for m in result]
        assert set(ids) == {"host", "switch", "legacy"}
        legacy = next(m for m in result if m["model_id"] == "legacy")
        assert legacy["is_visible"] is True

    def test_default_sort_passes_order_id_to_query(self, fake_graph):
        fake_graph.query_entity.return_value = ([], 0)
        ModelManage.search_model(language="en")
        kwargs = fake_graph.query_entity.call_args.kwargs
        assert kwargs.get("order") == "order_id"
        assert kwargs.get("order_type") == "ASC"


class TestUpdateModelOrders:
    def test_writes_order_and_visibility(self, fake_graph):
        fake_graph.query_entity.return_value = (
            [{"_id": 101, "model_id": "host"}], 1,
        )
        ModelManage.update_model_orders([
            {"model_id": "host", "order_id": 3, "is_visible": False},
        ])
        args, _ = fake_graph.set_entity_properties.call_args
        label, ids, props, *_ = args
        assert ids == [101]
        assert props == {"order_id": 3, "is_visible": False}

    def test_omits_visibility_if_not_provided(self, fake_graph):
        fake_graph.query_entity.return_value = (
            [{"_id": 101, "model_id": "host"}], 1,
        )
        ModelManage.update_model_orders([
            {"model_id": "host", "order_id": 3},
        ])
        args, _ = fake_graph.set_entity_properties.call_args
        _, _, props, *_ = args
        assert props == {"order_id": 3}


class TestSearchClassificationVisibility:
    def _classifications(self):
        return [
            {"classification_id": "infra", "classification_name": "Infra",
             "order": 2, "is_visible": True},
            {"classification_id": "biz", "classification_name": "Biz",
             "order": 0, "is_visible": False},
            {"classification_id": "legacy", "classification_name": "Legacy"},
        ]

    def test_default_filters_hidden_and_sorts(self, fake_graph):
        fake_graph.query_entity.side_effect = [
            (self._classifications(), 3),
            ([], 0),
        ]
        result = ClassificationManage.search_model_classification(language="en")
        ids = [c["classification_id"] for c in result]
        assert ids == ["infra", "legacy"]
        assert all(c["is_visible"] is True for c in result)

    def test_include_hidden_returns_all_sorted(self, fake_graph):
        fake_graph.query_entity.side_effect = [
            (self._classifications(), 3),
            ([], 0),
        ]
        result = ClassificationManage.search_model_classification(
            language="en", include_hidden=True,
        )
        ids = [c["classification_id"] for c in result]
        assert ids == ["biz", "infra", "legacy"]
        legacy = next(c for c in result if c["classification_id"] == "legacy")
        assert legacy["order"] == 999
        assert legacy["is_visible"] is True
