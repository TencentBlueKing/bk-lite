"""统一 OpenAPI 网关：CMDB 实例读写与关联双租户契约。"""

from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.cmdb.tests.openapi_gateway_support import (
    TEAM_A2_UUID,
    TEAM_A_UUID,
    TEAM_B_UUID,
    auth,
    make_tenant,
    start_cmdb_gateway_catalog,
    stop_cmdb_gateway_catalog,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

INSTANCE_URL = "/openapi/v1/cmdb/instance"
CREATE_URL = "/openapi/v1/cmdb/instance-create"
ASSOCIATIONS_URL = "/openapi/v1/cmdb/instance-associations"
ASSOCIATION_URL = "/openapi/v1/cmdb/instance-association"


@pytest.fixture
def tenants():
    return SimpleNamespace(
        a=make_tenant(team_name="cmdb-mut-a", username="cmdb-mut-a", domain="a.test.com"),
        b=make_tenant(team_name="cmdb-mut-b", username="cmdb-mut-b", domain="b.test.com"),
    )


@pytest.fixture
def catalog(tenants):
    item = start_cmdb_gateway_catalog(tenants)
    yield item
    stop_cmdb_gateway_catalog(item)


def test_api_tenant_can_create_instance_in_own_org(tenants, catalog):
    response = APIClient().post(
        CREATE_URL,
        {"model_id": "host", "attrs": {"inst_name": "host-new"}},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["organization"] == [tenants.a.team.id]
    assert catalog.calls.create[0]["allowed_org_ids"] == [tenants.a.team.id]
    assert catalog.calls.create[0]["data"]["organization"] == [tenants.a.team.id]


def test_api_tenant_create_does_not_belong_to_other_org(tenants, catalog):
    response = APIClient().post(
        CREATE_URL,
        {"model_id": "host", "attrs": {"inst_name": "host-b-new"}},
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["organization"] == [tenants.b.team.id]
    assert tenants.a.team.id not in catalog.calls.create[0]["allowed_org_ids"]
    assert tenants.a.team.id not in catalog.calls.create[0]["data"]["organization"]


def test_instance_create_forged_team_is_rejected(tenants, catalog):
    response = APIClient().post(
        CREATE_URL,
        {"model_id": "host", "attrs": {"inst_name": "forged"}, "team": tenants.b.team.id},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.create == []


def test_api_tenant_can_read_own_instance(tenants, catalog):
    response = APIClient().get(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID},
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["inst_name"] == "host-a"
    assert response.json()["data"]["organization"] == [tenants.a.team.id]


def test_api_tenant_cannot_read_other_org_instance(tenants, catalog):
    response = APIClient().get(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID},
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert response.json()["message"] == "实例不存在"


def test_instance_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID, "team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_update_own_instance(tenants, catalog):
    response = APIClient().put(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID, "attrs": {"inst_name": "host-a-renamed"}},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["inst_name"] == "host-a-renamed"
    assert catalog.calls.update[0]["allowed_org_ids"] == [tenants.a.team.id]


def test_api_tenant_cannot_update_other_org_instance(tenants, catalog):
    response = APIClient().put(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID, "attrs": {"inst_name": "hijacked"}},
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"
    assert catalog.calls.update == []


def test_instance_update_forged_team_is_rejected(tenants, catalog):
    response = APIClient().put(
        INSTANCE_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "attrs": {"inst_name": "forged"},
            "team": tenants.b.team.id,
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.update == []


def test_api_tenant_can_delete_own_instance(tenants, catalog):
    response = APIClient().delete(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["deleted"] == [TEAM_A_UUID]
    assert catalog.calls.delete == [[TEAM_A_UUID]]


def test_api_tenant_cannot_delete_other_org_instance(tenants, catalog):
    response = APIClient().delete(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID},
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"
    assert catalog.calls.delete == []
    assert any(row["inst_uuid"] == TEAM_A_UUID for row in catalog.store[tenants.a.team.id])


def test_instance_delete_forged_team_is_rejected(tenants, catalog):
    response = APIClient().delete(
        INSTANCE_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID, "team": tenants.b.team.id},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.delete == []


def test_api_tenant_can_batch_create_in_own_org(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-create",
        {"model_id": "host", "items": [{"inst_name": "batch-a"}]},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["created"][0]["organization"] == [tenants.a.team.id]
    assert catalog.calls.batch_create[0]["allowed_org_ids"] == [tenants.a.team.id]


def test_api_tenant_batch_create_does_not_belong_to_other_org(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-create",
        {"model_id": "host", "items": [{"inst_name": "batch-b"}]},
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 200, response.json()
    assert tenants.a.team.id not in catalog.calls.batch_create[0]["allowed_org_ids"]


def test_batch_create_forged_team_is_rejected(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-create",
        {"model_id": "host", "items": [{"inst_name": "forged"}], "team": tenants.b.team.id},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.batch_create == []


def test_api_tenant_can_batch_update_own_instances(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-update",
        {"model_id": "host", "inst_uuids": [TEAM_A_UUID], "update_data": {"inst_name": "batch-renamed"}},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert catalog.calls.batch_update[0]["inst_uuids"] == [TEAM_A_UUID]


def test_api_tenant_cannot_batch_update_other_org_instances(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-update",
        {"model_id": "host", "inst_uuids": [TEAM_A_UUID], "update_data": {"inst_name": "hijacked"}},
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"
    assert catalog.calls.batch_update == []


def test_batch_update_forged_team_is_rejected(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-update",
        {
            "model_id": "host",
            "inst_uuids": [TEAM_A_UUID],
            "update_data": {"inst_name": "forged"},
            "team": tenants.b.team.id,
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.batch_update == []


def test_api_tenant_can_batch_delete_own_instances(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-delete",
        {"model_id": "host", "inst_uuids": [TEAM_A2_UUID]},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["deleted"] == [TEAM_A2_UUID]
    assert catalog.calls.delete == [[TEAM_A2_UUID]]


def test_api_tenant_cannot_batch_delete_other_org_instances(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-delete",
        {"model_id": "host", "inst_uuids": [TEAM_A_UUID]},
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"
    assert catalog.calls.delete == []


def test_batch_delete_forged_team_is_rejected(tenants, catalog):
    response = APIClient().post(
        "/openapi/v1/cmdb/instance-batch-delete",
        {"model_id": "host", "inst_uuids": [TEAM_A_UUID], "team": tenants.b.team.id},
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.delete == []


def test_api_tenant_can_list_own_instance_associations(tenants, catalog):
    response = APIClient().get(
        ASSOCIATIONS_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID},
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"][0]["inst_list"][0]["inst_uuid"] == TEAM_A2_UUID


def test_api_tenant_cannot_list_other_org_instance_associations(tenants, catalog):
    response = APIClient().get(
        ASSOCIATIONS_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID},
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"


def test_instance_associations_forged_team_is_rejected(tenants, catalog):
    response = APIClient().get(
        ASSOCIATIONS_URL,
        {"model_id": "host", "inst_uuid": TEAM_A_UUID, "team": str(tenants.b.team.id)},
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_create_association_in_own_org(tenants, catalog):
    response = APIClient().post(
        ASSOCIATIONS_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "model_asst_id": "host_run_host",
            "target_model_id": "host",
            "target_inst_uuid": TEAM_A2_UUID,
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert catalog.calls.association_create[0]["src_inst_uuid"] == TEAM_A_UUID
    assert catalog.calls.association_create[0]["dst_inst_uuid"] == TEAM_A2_UUID


def test_api_tenant_cannot_create_association_to_other_org_instance(tenants, catalog):
    response = APIClient().post(
        ASSOCIATIONS_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "model_asst_id": "host_run_host",
            "target_model_id": "host",
            "target_inst_uuid": TEAM_B_UUID,
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"
    assert catalog.calls.association_create == []


def test_association_create_forged_team_is_rejected(tenants, catalog):
    response = APIClient().post(
        ASSOCIATIONS_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "model_asst_id": "host_run_host",
            "target_model_id": "host",
            "target_inst_uuid": TEAM_A2_UUID,
            "team": tenants.b.team.id,
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.association_create == []


def test_api_tenant_can_delete_own_association(tenants, catalog):
    response = APIClient().delete(
        ASSOCIATION_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "dst_inst_uuid": TEAM_A2_UUID,
            "model_asst_id": "host_run_host",
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert catalog.calls.association_delete[0]["src_inst_uuid"] == TEAM_A_UUID


def test_api_tenant_cannot_delete_other_org_association(tenants, catalog):
    response = APIClient().delete(
        ASSOCIATION_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "dst_inst_uuid": TEAM_A2_UUID,
            "model_asst_id": "host_run_host",
        },
        format="json",
        **auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "实例不存在"
    assert catalog.calls.association_delete == []


def test_association_delete_forged_team_is_rejected(tenants, catalog):
    response = APIClient().delete(
        ASSOCIATION_URL,
        {
            "model_id": "host",
            "inst_uuid": TEAM_A_UUID,
            "dst_inst_uuid": TEAM_A2_UUID,
            "model_asst_id": "host_run_host",
            "team": tenants.b.team.id,
        },
        format="json",
        **auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert catalog.calls.association_delete == []
