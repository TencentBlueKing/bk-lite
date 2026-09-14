"""CMDB LLM 相关 NATS handler 契约。"""

import pytest

from apps.cmdb.nats.nats import get_instance_by_uuid, list_instances_for_llm, search_models_for_llm

pytestmark = pytest.mark.django_db


def test_get_instance_by_uuid_requires_protocol_and_uuid():
    with pytest.raises(ValueError, match="protocol"):
        get_instance_by_uuid({"inst_uuid": "u1"})
    with pytest.raises(ValueError, match="inst_uuid"):
        get_instance_by_uuid({"protocol_version": "2"})


def test_get_instance_by_uuid_requires_permission_context(mocker):
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuid", return_value={"inst_uuid": "u1", "model_id": "host"})
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        get_instance_by_uuid({"protocol_version": "2", "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "user_info": {}})


def test_list_instances_for_llm_requires_permission(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        list_instances_for_llm(
            {
                "protocol_version": "2",
                "model_id": "host",
                "user_info": {"user": "alice", "domain": "d.com", "team": 1, "include_children": False},
            }
        )


def test_search_models_for_llm_requires_permission(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_model_permission_map", return_value=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        search_models_for_llm({"user_info": {"user": "alice", "domain": "d.com", "team": 1, "include_children": False}})


def test_search_models_for_llm_filters_in_process(mocker):
    mocker.patch(
        "apps.cmdb.nats.nats._build_nats_model_permission_map",
        return_value={1: {"permission_instances_map": {}, "inst_names": []}},
    )
    mocker.patch("apps.cmdb.nats.nats.get_default_group_id", return_value=[1])
    mocker.patch(
        "apps.cmdb.nats.nats.ModelManage.search_model",
        return_value=[
            {"model_id": "keep", "model_name": "Keep", "classification_id": "llm_e2e"},
            {"model_id": "drop", "model_name": "Drop", "classification_id": "other"},
            {"model_id": "other_keep", "model_name": "Other", "classification_id": "llm_e2e"},
        ],
    )
    mocker.patch(
        "apps.cmdb.nats.nats._llm_has_model_view",
        side_effect=lambda model, _permission_map: model["model_id"] != "drop",
    )
    mocker.patch("apps.cmdb.nats.nats._serialize_instance_for_transport", side_effect=lambda item: item)

    listed = search_models_for_llm(
        {
            "user_info": {"user": "alice", "domain": "d.com", "team": 1, "include_children": False},
            "classification_id": "llm_e2e",
        }
    )

    assert [item["model_id"] for item in listed] == ["keep", "other_keep"]
