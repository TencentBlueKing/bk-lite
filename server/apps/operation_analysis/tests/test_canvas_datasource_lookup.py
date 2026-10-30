import pytest

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.canvas_datasource_lookup import build_canvas_datasource_payloads, denied_canvas_datasource_stub


def test_denied_stub_exposes_id_has_auth_and_required_app():
    stub = denied_canvas_datasource_stub(12, " alarm ")
    assert stub == {"id": 12, "hasAuth": False, "required_app": "alarm"}
    assert set(stub) == {"id", "hasAuth", "required_app"}
    assert "rest_api" not in stub


def test_denied_stub_keeps_missing_required_app_null():
    stub = denied_canvas_datasource_stub(12)
    assert stub["required_app"] is None


@pytest.mark.django_db
def test_build_canvas_datasource_payloads_returns_denied_and_allowed():
    allowed = DataSourceAPIModel.objects.create(name="allowed", groups=[1], rest_api="x/y")
    denied = DataSourceAPIModel.objects.create(
        name="denied",
        groups=[2],
        rest_api="a/b",
        required_app="alarm",
    )

    payloads = build_canvas_datasource_payloads(
        ordered_ids=[allowed.id, denied.id, 999],
        instances=[allowed, denied],
        current_team=1,
        serialize_allowed=lambda item: {"id": item.id, "name": item.name},
    )

    assert payloads[0] == {"id": allowed.id, "name": allowed.name, "hasAuth": True}
    assert payloads[1] == {"id": denied.id, "hasAuth": False, "required_app": "alarm"}
    assert len(payloads) == 2
    assert "name" not in payloads[1]
    assert "params" not in payloads[1]
    assert "rest_api" not in payloads[1]


@pytest.mark.django_db
def test_build_canvas_datasource_payloads_skips_deleted_ids():
    allowed = DataSourceAPIModel.objects.create(name="allowed", groups=[1], rest_api="x/y")

    payloads = build_canvas_datasource_payloads(
        ordered_ids=[allowed.id, 404],
        instances=[allowed],
        current_team=1,
        serialize_allowed=lambda item: {"id": item.id, "name": item.name},
    )

    assert [item["id"] for item in payloads] == [allowed.id]
