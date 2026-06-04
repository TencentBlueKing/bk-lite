"""Tests for model/classification visibility and layout features."""

import pytest
from unittest.mock import MagicMock

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
