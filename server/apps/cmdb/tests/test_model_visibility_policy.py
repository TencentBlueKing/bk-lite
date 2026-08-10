"""CMDB 业务模型有效可见性策略测试。"""

from unittest.mock import MagicMock

import pytest

from apps.cmdb.constants.constants import CLASSIFICATION, MODEL
from apps.cmdb.services.model_visibility import BusinessModelVisibility


@pytest.fixture
def graph_boundary(monkeypatch):
    graph = MagicMock()
    graph.__enter__.return_value = graph
    graph.__exit__.return_value = False

    def query_entity(label, params=None, **kwargs):
        if label == MODEL:
            return (
                [
                    {
                        "model_id": "host",
                        "model_name": "Host",
                        "classification_id": "infra",
                        "is_visible": True,
                    },
                    {
                        "model_id": "docker",
                        "model_name": "Docker",
                        "classification_id": "container",
                        "is_visible": True,
                    },
                ],
                2,
            )
        if label == CLASSIFICATION:
            return (
                [
                    {"classification_id": "infra", "is_visible": True},
                    {"classification_id": "container", "is_visible": False},
                ],
                2,
            )
        raise AssertionError(f"unexpected label: {label}")

    graph.query_entity.side_effect = query_entity
    monkeypatch.setattr(
        "apps.cmdb.services.model_visibility.GraphClient",
        lambda: graph,
    )
    return graph


def test_parent_classification_hidden_makes_model_invisible(graph_boundary):
    visible = BusinessModelVisibility.resolve(["host", "docker"])

    assert list(visible) == ["host"]
    assert visible["host"]["model_name"] == "Host"


def test_association_with_hidden_endpoint_is_omitted(graph_boundary):
    associations = [
        {
            "model_asst_id": "host_run_docker",
            "src_model_id": "host",
            "dst_model_id": "docker",
        }
    ]

    assert BusinessModelVisibility.filter_associations(associations) == []


def test_visible_association_contains_endpoint_names(graph_boundary):
    associations = [
        {
            "model_asst_id": "host_link_host",
            "src_model_id": "host",
            "dst_model_id": "host",
        }
    ]

    result = BusinessModelVisibility.filter_associations(associations)

    assert result[0]["src_model_name"] == "Host"
    assert result[0]["dst_model_name"] == "Host"


def test_model_record_marked_hidden_is_not_business_visible():
    assert (
        BusinessModelVisibility.is_visible(
            {"model_id": "docker", "is_visible": False}
        )
        is False
    )
