from uuid import UUID

import pytest

from apps.cmdb.services.instance_identity import (
    cmdb_link_identity,
    collect_cmdb_id_candidates,
    ensure_graph_instance_identity,
    ensure_instance_identity_immutable,
    expand_cmdb_id_lookup_candidates,
    normalize_inst_uuid,
    optional_graph_id,
    optional_inst_uuid,
    prepare_edge_endpoint_properties,
    prepare_new_instance_identity,
)
from apps.core.exceptions.base_app_exception import BaseAppException


def test_new_cmdb_instance_gets_canonical_uuid4():
    prepared = prepare_new_instance_identity({"inst_name": "host-01"})

    parsed = UUID(prepared["inst_uuid"])
    assert parsed.version == 4
    assert prepared["inst_uuid"] == str(parsed)
    assert prepared["inst_name"] == "host-01"


def test_normal_instance_creation_rejects_client_supplied_uuid():
    with pytest.raises(BaseAppException, match="inst_uuid 是系统保留字段"):
        prepare_new_instance_identity(
            {
                "inst_name": "host-01",
                "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
            }
        )


def test_instance_uuid_cannot_be_updated_even_to_same_value():
    with pytest.raises(BaseAppException, match="inst_uuid 不可修改"):
        ensure_instance_identity_immutable({"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"})


def test_instance_uuid_input_is_normalized_to_canonical_uuid4():
    assert normalize_inst_uuid("63E4A531-B6BB-43CC-9EAE-8EB8A09F795E") == ("63e4a531-b6bb-43cc-9eae-8eb8a09f795e")


@pytest.mark.parametrize(
    "value",
    ["123", "", None, "550e8400-e29b-11d4-a716-446655440000"],
)
def test_invalid_or_non_v4_instance_uuid_is_rejected(value):
    with pytest.raises(BaseAppException, match="inst_uuid 必须是 UUIDv4"):
        normalize_inst_uuid(value)


def test_graph_boundary_adds_uuid_only_to_instance():
    instance = ensure_graph_instance_identity("instance", {"inst_name": "h1"})
    model = ensure_graph_instance_identity("model", {"model_id": "host"})

    assert UUID(instance["inst_uuid"]).version == 4
    assert model == {"model_id": "host"}


def test_graph_boundary_preserves_valid_uuid_canonically():
    result = ensure_graph_instance_identity(
        "instance",
        {"inst_uuid": "63E4A531-B6BB-43CC-9EAE-8EB8A09F795E"},
    )

    assert result["inst_uuid"] == "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


def test_edge_write_persists_uuid_endpoints_and_strips_numeric_ids():
    result = prepare_edge_endpoint_properties(
        {
            "model_asst_id": "host_run_on_host",
            "src_inst_id": 1,
            "dst_inst_id": 2,
            "src_inst_uuid": "63E4A531-B6BB-43CC-9EAE-8EB8A09F795E",
        },
        dst_inst_uuid="123e4567-e89b-42d3-a456-426614174000",
    )

    assert result == {
        "model_asst_id": "host_run_on_host",
        "src_inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
        "dst_inst_uuid": "123e4567-e89b-42d3-a456-426614174000",
    }


def test_edge_write_rejects_missing_uuid_endpoints():
    with pytest.raises(BaseAppException, match="边端点必须包含"):
        prepare_edge_endpoint_properties({"model_asst_id": "x", "src_inst_id": 1})


def test_optional_inst_uuid_and_graph_id():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    assert optional_inst_uuid(inst_uuid) == inst_uuid
    assert optional_inst_uuid("42") is None
    assert optional_graph_id(42) == "42"
    assert optional_graph_id(inst_uuid) is None


def test_cmdb_link_identity_prefers_uuid_and_keeps_graph_alias():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    canonical, aliases = cmdb_link_identity({"_id": 7, "inst_uuid": inst_uuid})
    assert canonical == inst_uuid
    assert aliases == [inst_uuid, "7"]


def test_collect_cmdb_id_candidates_dedupes_nested_values():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    assert collect_cmdb_id_candidates(inst_uuid, ["7", inst_uuid], None) == [inst_uuid, "7"]


def test_expand_cmdb_id_lookup_candidates_adds_graph_id(monkeypatch):
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"

    class _InstanceManage:
        @staticmethod
        def query_entity_by_uuid(value):
            assert value == inst_uuid
            return {"_id": 7, "inst_uuid": inst_uuid}

        @staticmethod
        def query_entity_by_id(_value):
            raise AssertionError("should not query by graph id")

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", _InstanceManage)
    assert expand_cmdb_id_lookup_candidates(inst_uuid) == [inst_uuid, "7"]
