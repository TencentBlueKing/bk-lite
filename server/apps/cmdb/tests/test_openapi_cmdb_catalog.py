"""统一 OpenAPI 网关：CMDB 模型目录双租户契约。"""

from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.cmdb.tests.openapi_gateway_support import auth, make_tenant, start_cmdb_gateway_catalog, stop_cmdb_gateway_catalog

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def tenants():
    return SimpleNamespace(
        a=make_tenant(team_name="cmdb-gw-a", username="cmdb-gw-a", domain="a.test.com"),
        b=make_tenant(team_name="cmdb-gw-b", username="cmdb-gw-b", domain="b.test.com"),
    )


@pytest.fixture
def catalog(tenants):
    item = start_cmdb_gateway_catalog(tenants)
    yield item
    stop_cmdb_gateway_catalog(item)


def test_api_tenant_can_list_own_classifications(tenants, catalog):
    response = APIClient().get("/openapi/v1/cmdb/classifications", **auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = [item["classification_id"] for item in response.json()["data"]]
    assert "class-a" in ids
    assert "class-common" in ids
    assert "class-b" not in ids


def test_api_tenant_cannot_list_other_org_classifications(tenants, catalog):
    response = APIClient().get("/openapi/v1/cmdb/classifications", **auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = [item["classification_id"] for item in response.json()["data"]]
    assert "class-b" in ids
    assert "class-a" not in ids


def test_classifications_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/classifications",
        {"team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_models(tenants, catalog):
    response = APIClient().get("/openapi/v1/cmdb/models", **auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = [item["model_id"] for item in response.json()["data"]]
    assert "host-a" in ids
    assert "host" in ids
    assert "host-b" not in ids


def test_api_tenant_cannot_list_other_org_models(tenants, catalog):
    response = APIClient().get("/openapi/v1/cmdb/models", **auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = [item["model_id"] for item in response.json()["data"]]
    assert "host-b" in ids
    assert "host-a" not in ids


def test_models_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/models",
        {"team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_read_own_model(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model",
        {"model_id": "host-a"},
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["model_id"] == "host-a"


def test_api_tenant_cannot_read_other_org_model(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model",
        {"model_id": "host-a"},
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert response.json()["message"] == "模型不存在"


def test_model_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model",
        {"model_id": "host-a", "team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_read_own_model_attributes(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model-attributes",
        {"model_id": "host-a"},
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"][0]["attr_id"] == "inst_name"


def test_api_tenant_cannot_read_other_org_model_attributes(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model-attributes",
        {"model_id": "host-a"},
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "模型不存在"


def test_model_attributes_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model-attributes",
        {"model_id": "host-a", "team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_read_own_model_associations(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model-associations",
        {"model_id": "host"},
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"][0]["model_asst_id"] == "host_run_host"


def test_api_tenant_cannot_read_other_org_model_associations(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model-associations",
        {"model_id": "host-a"},
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "模型不存在"


def test_model_associations_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        "/openapi/v1/cmdb/model-associations",
        {"model_id": "host", "team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
