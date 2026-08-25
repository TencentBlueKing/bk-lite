from unittest.mock import patch

import django
import pytest

django.setup()

from apps.cmdb.nats import nats as N  # noqa: E402

INST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_by_uuid_hides_graph_id(mock_im):
    mock_im.instance_update_by_uuid.return_value = {
        "_id": 123,
        "inst_uuid": INST_UUID,
        "inst_name": "host-01",
    }

    result = N.update_instance(
        {
            "protocol_version": "2",
            "inst_uuid": INST_UUID,
            "update_attr": {"ip": "1.2.3.4"},
            "operator": "admin",
            "allowed_org_ids": [3],
        }
    )

    assert result == {"inst_uuid": INST_UUID, "inst_name": "host-01"}
    mock_im.instance_update_by_uuid.assert_called_once_with(
        user_groups=[{"id": 3}],
        roles=[],
        inst_uuid=INST_UUID,
        update_attr={"ip": "1.2.3.4"},
        operator="admin",
        allowed_org_ids=[3],
        skip_permission_check=False,
    )


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_missing_auth_context_rejects(mock_im):
    with pytest.raises(ValueError, match="authorization scope"):
        N.update_instance(
            {
                "protocol_version": "2",
                "inst_uuid": INST_UUID,
                "update_attr": {"organization": [3]},
            }
        )
    mock_im.instance_update_by_uuid.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_explicit_scope_is_forwarded(mock_im):
    mock_im.instance_update_by_uuid.return_value = {"inst_uuid": INST_UUID}
    N.update_instance(
        {
            "protocol_version": "2",
            "inst_uuid": INST_UUID,
            "update_attr": {"organization": [3]},
            "allowed_org_ids": [3, 9],
        }
    )
    kwargs = mock_im.instance_update_by_uuid.call_args.kwargs
    assert kwargs["allowed_org_ids"] == [3, 9]
    assert kwargs["user_groups"] == [{"id": 3}, {"id": 9}]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_organization_outside_scope_rejects(mock_im):
    with pytest.raises(ValueError, match="organization .*授权范围"):
        N.update_instance(
            {
                "protocol_version": "2",
                "inst_uuid": INST_UUID,
                "update_attr": {"organization": [9]},
                "allowed_org_ids": [3],
            }
        )
    mock_im.instance_update_by_uuid.assert_not_called()


@pytest.mark.parametrize("payload", [{"inst_id": 1}, {"_id": 1}, {"inst_ids": [1]}])
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_rejects_legacy_locators(mock_im, payload):
    with pytest.raises(ValueError, match="legacy numeric locators"):
        N.update_instance(
            {
                "protocol_version": "2",
                **payload,
                "update_attr": {"k": "v"},
                "allowed_org_ids": [1],
            }
        )
    mock_im.instance_update_by_uuid.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_missing_uuid_raises(mock_im):
    with pytest.raises(ValueError, match="inst_uuid is required"):
        N.update_instance(
            {
                "protocol_version": "2",
                "update_attr": {"k": "v"},
                "allowed_org_ids": [1],
            }
        )
    mock_im.instance_update_by_uuid.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_empty_update_attr_raises(mock_im):
    with pytest.raises(ValueError, match="update_attr is required"):
        N.update_instance({"protocol_version": "2", "inst_uuid": INST_UUID, "update_attr": {}})
    mock_im.instance_update_by_uuid.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_requires_protocol_version(mock_im):
    with pytest.raises(ValueError, match="unsupported CMDB identity protocol version"):
        N.update_instance({"inst_uuid": INST_UUID, "update_attr": {"k": "v"}, "allowed_org_ids": [1]})
    mock_im.instance_update_by_uuid.assert_not_called()
