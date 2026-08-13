from unittest.mock import patch

import django
import pytest

django.setup()

from apps.cmdb.nats import nats as N  # noqa: E402

UUID_1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
UUID_2 = "7de0c6de-f841-44b1-846d-2d75a7c59c50"


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_returns_uuid_without_graph_id(mock_im):
    mock_im.instance_create.return_value = {"_id": 7, "inst_uuid": UUID_1, "inst_name": "host-01"}
    result = N.create_instance(
        {
            "protocol_version": "2",
            "model_id": "host",
            "instance_info": {"ip": "1.2.3.4"},
            "operator": "admin",
            "allowed_org_ids": [3],
        }
    )
    assert result == {"inst_uuid": UUID_1, "inst_name": "host-01"}
    mock_im.instance_create.assert_called_once_with(
        model_id="host",
        instance_info={"ip": "1.2.3.4"},
        operator="admin",
        allowed_org_ids=[3],
    )


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_missing_auth_context_rejects(mock_im):
    with pytest.raises(ValueError, match="authorization scope"):
        N.create_instance({"protocol_version": "2", "model_id": "host", "instance_info": {"organization": [3]}})
    mock_im.instance_create.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_explicit_allowed_org_ids(mock_im):
    mock_im.instance_create.return_value = {"inst_uuid": UUID_1}
    N.create_instance(
        {
            "protocol_version": "2",
            "model_id": "host",
            "instance_info": {"organization": [3]},
            "allowed_org_ids": [3, 9],
        }
    )
    _, kwargs = mock_im.instance_create.call_args
    assert kwargs["allowed_org_ids"] == [3, 9]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_organization_outside_scope_rejects(mock_im):
    with pytest.raises(ValueError, match="organization .*授权范围"):
        N.create_instance(
            {
                "protocol_version": "2",
                "model_id": "host",
                "instance_info": {"organization": [9]},
                "allowed_org_ids": [3],
            }
        )
    mock_im.instance_create.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_default_operator(mock_im):
    mock_im.instance_create.return_value = {"inst_uuid": UUID_1}
    N.create_instance(
        {
            "protocol_version": "2",
            "model_id": "host",
            "instance_info": {"k": "v"},
            "allowed_org_ids": [1],
        }
    )
    _, kwargs = mock_im.instance_create.call_args
    assert kwargs["operator"] == ""


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"instance_info": {"k": "v"}}, "model_id is required"),
        ({"model_id": "host", "instance_info": {}}, "instance_info is required"),
    ],
)
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_validates_required_fields(mock_im, payload, message):
    with pytest.raises(ValueError, match=message):
        N.create_instance({**payload, "protocol_version": "2", "allowed_org_ids": [1]})
    mock_im.instance_create.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_requires_protocol_version(mock_im):
    with pytest.raises(ValueError, match="unsupported CMDB identity protocol version"):
        N.create_instance({"model_id": "host", "instance_info": {"k": "v"}, "allowed_org_ids": [1]})
    mock_im.instance_create.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_by_uuids(mock_im):
    result = N.delete_instance(
        {
            "protocol_version": "2",
            "inst_uuids": [UUID_1, UUID_2],
            "operator": "admin",
            "allowed_org_ids": [3],
        }
    )
    assert result == {"result": True, "deleted": [UUID_1, UUID_2]}
    mock_im.instance_batch_delete_by_uuids.assert_called_once_with(user_groups=[{"id": 3}], roles=[], inst_uuids=[UUID_1, UUID_2], operator="admin")


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_single_uuid_and_service_scope(mock_im):
    result = N.delete_instance({"protocol_version": "2", "inst_uuid": UUID_1, "service_scope": {"allowed_org_ids": [4]}})
    assert result == {"result": True, "deleted": [UUID_1]}
    assert mock_im.instance_batch_delete_by_uuids.call_args.kwargs["user_groups"] == [{"id": 4}]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_with_user_info_scope(mock_im):
    result = N.delete_instance({"protocol_version": "2", "inst_uuid": UUID_1, "user_info": {"allowed_org_ids": [5]}})
    assert result == {"result": True, "deleted": [UUID_1]}
    assert mock_im.instance_batch_delete_by_uuids.call_args.kwargs["user_groups"] == [{"id": 5}]


@pytest.mark.parametrize("payload", [{"inst_ids": [1]}, {"inst_id": 1}, {"_id": 1}])
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_rejects_legacy_locators(mock_im, payload):
    with pytest.raises(ValueError, match="legacy numeric locators"):
        N.delete_instance({"protocol_version": "2", **payload, "allowed_org_ids": [1]})
    mock_im.instance_batch_delete_by_uuids.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_missing_auth_context_rejects(mock_im):
    with pytest.raises(ValueError, match="authorization scope"):
        N.delete_instance({"protocol_version": "2", "inst_uuid": UUID_1})
    mock_im.instance_batch_delete_by_uuids.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_empty_auth_scope_rejects(mock_im):
    with pytest.raises(ValueError, match="authorization scope"):
        N.delete_instance({"protocol_version": "2", "inst_uuid": UUID_1, "allowed_org_ids": []})
    mock_im.instance_batch_delete_by_uuids.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_missing_locator_raises(mock_im):
    with pytest.raises(ValueError, match="inst_uuids or inst_uuid"):
        N.delete_instance({"protocol_version": "2", "allowed_org_ids": [1]})
    mock_im.instance_batch_delete_by_uuids.assert_not_called()
