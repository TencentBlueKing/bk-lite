"""CMDB LLM 相关 NATS handler 契约。"""

import django
import pytest

django.setup()

from apps.cmdb.nats.nats import (  # noqa: E402
    batch_update_instances,
    create_instance_association_for_llm,
    create_instance_for_llm,
    delete_instance_association_for_llm,
    delete_instance_for_llm,
    get_instance_by_uuid,
    list_instances_for_llm,
    search_models_for_llm,
    update_instance_for_llm,
)

INST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
DST_UUID = "7de0c6de-f841-44b1-846d-2d75a7c59c50"
USER_INFO = {"user": "alice", "domain": "d.com", "team": 1, "include_children": False}
PERMISSION_MAP = {1: {"permission_instances_map": {}, "inst_names": []}}
HOST_INSTANCE = {
    "inst_uuid": INST_UUID,
    "model_id": "host",
    "inst_name": "box1",
    "organization": [1],
}


def _write_params(**extra):
    return {
        "protocol_version": "2",
        "user_info": USER_INFO,
        "operator": "alice",
        "allowed_org_ids": [1],
        **extra,
    }


def test_get_instance_by_uuid_requires_protocol_and_uuid():
    with pytest.raises(ValueError, match="protocol"):
        get_instance_by_uuid({"inst_uuid": "u1"})
    with pytest.raises(ValueError, match="inst_uuid"):
        get_instance_by_uuid({"protocol_version": "2"})


def test_get_instance_by_uuid_requires_permission_context(mocker):
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuid", return_value={"inst_uuid": "u1", "model_id": "host"})
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        get_instance_by_uuid({"protocol_version": "2", "inst_uuid": INST_UUID, "user_info": {}})


def test_list_instances_for_llm_requires_permission(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        list_instances_for_llm(
            {
                "protocol_version": "2",
                "model_id": "host",
                "user_info": USER_INFO,
            }
        )


def test_search_models_for_llm_requires_permission(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_model_permission_map", return_value=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        search_models_for_llm({"user_info": USER_INFO})


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
            "user_info": USER_INFO,
            "classification_id": "llm_e2e",
        }
    )

    assert [item["model_id"] for item in listed] == ["keep", "other_keep"]


def _patch_create_permission_lookups(mocker, *, instance_operate=False, model_operate=False, permission_map=PERMISSION_MAP):
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=permission_map)
    mocker.patch("apps.cmdb.nats.nats.ModelManage.search_model_info", return_value={"model_id": "host", "group": [1]})
    mocker.patch("apps.cmdb.nats.nats.BusinessModelVisibility.is_visible", return_value=True)
    mocker.patch("apps.cmdb.nats.nats._llm_has_model_permission", return_value=model_operate)
    mocker.patch("apps.cmdb.nats.nats._llm_has_instance_permission", return_value=instance_operate)
    return mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_create")


def test_create_instance_for_llm_requires_user_info(mocker):
    create = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_create")
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        create_instance_for_llm(
            {
                "protocol_version": "2",
                "model_id": "host",
                "instance_info": {"inst_name": "box", "organization": [1]},
                "allowed_org_ids": [1],
            }
        )
    create.assert_not_called()


def test_create_instance_for_llm_rejects_without_operate(mocker):
    create = _patch_create_permission_lookups(mocker, instance_operate=False, model_operate=False)
    with pytest.raises(ValueError, match="insufficient instance permission"):
        create_instance_for_llm(
            _write_params(
                model_id="host",
                instance_info={"inst_name": "box", "organization": [1]},
            )
        )
    create.assert_not_called()


def test_create_instance_for_llm_rejects_missing_permission_map(mocker):
    create = _patch_create_permission_lookups(mocker, permission_map=None)
    with pytest.raises(ValueError, match="insufficient CMDB permission"):
        create_instance_for_llm(
            _write_params(
                model_id="host",
                instance_info={"inst_name": "box", "organization": [1]},
            )
        )
    create.assert_not_called()


def test_create_instance_for_llm_allows_instance_operate(mocker):
    create = _patch_create_permission_lookups(mocker, instance_operate=True, model_operate=False)
    create.return_value = {"_id": 9, "inst_uuid": INST_UUID, "inst_name": "box"}
    result = create_instance_for_llm(
        _write_params(
            model_id="host",
            instance_info={"inst_name": "box", "organization": [1]},
        )
    )
    assert result == {"inst_uuid": INST_UUID, "inst_name": "box"}
    create.assert_called_once()


def test_create_instance_for_llm_allows_model_operate(mocker):
    create = _patch_create_permission_lookups(mocker, instance_operate=False, model_operate=True)
    create.return_value = {"_id": 9, "inst_uuid": INST_UUID, "inst_name": "box"}
    result = create_instance_for_llm(
        _write_params(
            model_id="host",
            instance_info={"inst_name": "box", "organization": [1]},
        )
    )
    assert result["inst_uuid"] == INST_UUID
    create.assert_called_once()


def _patch_existing_instance_write(mocker, *, operate=False, instance=None, instances=None):
    instance = instance or HOST_INSTANCE
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=PERMISSION_MAP)
    mocker.patch("apps.cmdb.nats.nats._llm_has_instance_permission", return_value=operate)
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuid", return_value=instance)
    mocker.patch(
        "apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuids",
        return_value=instances if instances is not None else [instance],
    )


def test_update_instance_for_llm_rejects_without_operate(mocker):
    _patch_existing_instance_write(mocker, operate=False)
    update = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_update_by_uuid")
    with pytest.raises(ValueError, match="insufficient instance permission"):
        update_instance_for_llm(_write_params(inst_uuid=INST_UUID, update_attr={"inst_name": "n2"}))
    update.assert_not_called()


def test_update_instance_for_llm_allows_operate(mocker):
    _patch_existing_instance_write(mocker, operate=True)
    update = mocker.patch(
        "apps.cmdb.nats.nats.InstanceManage.instance_update_by_uuid",
        return_value={"_id": 3, "inst_uuid": INST_UUID, "inst_name": "n2"},
    )
    result = update_instance_for_llm(_write_params(inst_uuid=INST_UUID, update_attr={"inst_name": "n2"}))
    assert result == {"inst_uuid": INST_UUID, "inst_name": "n2"}
    update.assert_called_once()


def test_delete_instance_for_llm_rejects_without_operate(mocker):
    _patch_existing_instance_write(mocker, operate=False)
    delete = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_batch_delete_by_uuids")
    with pytest.raises(ValueError, match="insufficient instance permission"):
        delete_instance_for_llm(_write_params(inst_uuid=INST_UUID))
    delete.assert_not_called()


def test_delete_instance_for_llm_rejects_partial_batch_without_operate(mocker):
    src = dict(HOST_INSTANCE)
    dst = {"inst_uuid": DST_UUID, "model_id": "host", "inst_name": "box2", "organization": [1]}
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=PERMISSION_MAP)
    mocker.patch("apps.cmdb.nats.nats._llm_has_instance_permission", side_effect=[True, False])
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuids", return_value=[src, dst])
    delete = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_batch_delete_by_uuids")
    with pytest.raises(ValueError, match="insufficient instance permission"):
        delete_instance_for_llm(_write_params(inst_uuids=[INST_UUID, DST_UUID]))
    delete.assert_not_called()


def test_delete_instance_for_llm_allows_operate(mocker):
    _patch_existing_instance_write(mocker, operate=True)
    delete = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_batch_delete_by_uuids")
    result = delete_instance_for_llm(_write_params(inst_uuid=INST_UUID))
    assert result == {"result": True, "deleted": [INST_UUID]}
    delete.assert_called_once()


def test_batch_update_instances_rejects_without_operate(mocker):
    _patch_existing_instance_write(mocker, operate=False)
    update = mocker.patch("apps.cmdb.nats.nats.InstanceManage.batch_instance_update_by_uuids")
    with pytest.raises(ValueError, match="insufficient instance permission"):
        batch_update_instances(_write_params(inst_uuids=[INST_UUID], update_attr={"k": "v"}))
    update.assert_not_called()


def _association_endpoints():
    return [
        dict(HOST_INSTANCE),
        {"inst_uuid": DST_UUID, "model_id": "app", "inst_name": "app1", "organization": [1]},
    ]


def test_create_instance_association_for_llm_rejects_without_operate(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=PERMISSION_MAP)
    mocker.patch("apps.cmdb.nats.nats._llm_has_instance_permission", return_value=False)
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuids", return_value=_association_endpoints())
    create = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_association_create_by_uuid")
    with pytest.raises(ValueError, match="insufficient instance permission"):
        create_instance_association_for_llm(
            _write_params(src_inst_uuid=INST_UUID, dst_inst_uuid=DST_UUID, model_asst_id="host_run_app")
        )
    create.assert_not_called()


def test_delete_instance_association_for_llm_rejects_without_operate(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=PERMISSION_MAP)
    mocker.patch("apps.cmdb.nats.nats._llm_has_instance_permission", side_effect=[True, False])
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuids", return_value=_association_endpoints())
    delete = mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_association_delete_by_key")
    with pytest.raises(ValueError, match="insufficient instance permission"):
        delete_instance_association_for_llm(
            _write_params(src_inst_uuid=INST_UUID, dst_inst_uuid=DST_UUID, model_asst_id="host_run_app")
        )
    delete.assert_not_called()


def test_create_instance_association_for_llm_allows_operate(mocker):
    mocker.patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=PERMISSION_MAP)
    mocker.patch("apps.cmdb.nats.nats._llm_has_instance_permission", return_value=True)
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.query_entity_by_uuids", return_value=_association_endpoints())
    expected = {"src_inst_uuid": INST_UUID, "dst_inst_uuid": DST_UUID, "model_asst_id": "host_run_app"}
    mocker.patch("apps.cmdb.nats.nats.InstanceManage.instance_association_create_by_uuid", return_value=expected)
    result = create_instance_association_for_llm(
        _write_params(src_inst_uuid=INST_UUID, dst_inst_uuid=DST_UUID, model_asst_id="host_run_app")
    )
    assert result == expected
