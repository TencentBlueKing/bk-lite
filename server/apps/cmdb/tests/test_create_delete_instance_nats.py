"""CMDB NATS create_instance / delete_instance 处理器单元测试。

对照 apps/cmdb/nats/nats.py：参数校验、实例定位（inst_ids / inst_id / model_id+inst_name）、
对 InstanceManage.instance_create / instance_batch_delete 的委托与透传。
"""

from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats as N


# --------------------------------------------------------------------------
# create_instance
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_ok(mock_im):
    mock_im.instance_create.return_value = {"_id": 7, "inst_name": "host-01"}

    result = N.create_instance(
        {"model_id": "host", "instance_info": {"ip": "1.2.3.4"}, "operator": "admin"}
    )

    assert result == {"_id": 7, "inst_name": "host-01"}
    mock_im.instance_create.assert_called_once_with(
        model_id="host",
        instance_info={"ip": "1.2.3.4"},
        operator="admin",
        allowed_org_ids=None,
    )


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_org_scope_defaults_to_payload(mock_im):
    """带 organization 时默认放行其自身（机器接口无范围限制）。"""
    mock_im.instance_create.return_value = {"_id": 1}

    N.create_instance(
        {"model_id": "host", "instance_info": {"organization": [3, 5]}}
    )

    _, kwargs = mock_im.instance_create.call_args
    assert kwargs["allowed_org_ids"] == [3, 5]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_explicit_allowed_org_ids(mock_im):
    """显式传 allowed_org_ids 时按其限制。"""
    mock_im.instance_create.return_value = {"_id": 1}

    N.create_instance(
        {"model_id": "host", "instance_info": {"organization": [3]}, "allowed_org_ids": [3, 9]}
    )

    _, kwargs = mock_im.instance_create.call_args
    assert kwargs["allowed_org_ids"] == [3, 9]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_default_operator(mock_im):
    mock_im.instance_create.return_value = {"_id": 1}

    N.create_instance({"model_id": "host", "instance_info": {"k": "v"}})

    _, kwargs = mock_im.instance_create.call_args
    assert kwargs["operator"] == ""


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_missing_model_id_raises(mock_im):
    with pytest.raises(ValueError, match="model_id is required"):
        N.create_instance({"instance_info": {"k": "v"}})
    mock_im.instance_create.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_empty_info_raises(mock_im):
    with pytest.raises(ValueError, match="instance_info is required"):
        N.create_instance({"model_id": "host", "instance_info": {}})
    mock_im.instance_create.assert_not_called()


# --------------------------------------------------------------------------
# delete_instance
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_by_ids(mock_im):
    result = N.delete_instance({"inst_ids": [1, 2], "operator": "admin"})

    assert result == {"result": True, "deleted": [1, 2]}
    mock_im.search_inst.assert_not_called()
    mock_im.instance_batch_delete.assert_called_once_with(
        user_groups=[],
        roles=[],
        inst_ids=[1, 2],
        operator="admin",
    )


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_by_single_id(mock_im):
    result = N.delete_instance({"inst_id": 9})

    assert result == {"result": True, "deleted": [9]}
    _, kwargs = mock_im.instance_batch_delete.call_args
    assert kwargs["inst_ids"] == [9]
    assert kwargs["operator"] == ""


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_by_underscore_id(mock_im):
    N.delete_instance({"_id": 5})
    _, kwargs = mock_im.instance_batch_delete.call_args
    assert kwargs["inst_ids"] == [5]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_by_model_and_name(mock_im):
    mock_im.search_inst.return_value = ([{"_id": 55, "inst_name": "host-01"}], 1)

    result = N.delete_instance({"model_id": "host", "inst_name": "host-01"})

    assert result == {"result": True, "deleted": [55]}
    mock_im.search_inst.assert_called_once_with(model_id="host", inst_name="host-01")
    _, kwargs = mock_im.instance_batch_delete.call_args
    assert kwargs["inst_ids"] == [55]


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_missing_locator_raises(mock_im):
    with pytest.raises(ValueError, match="inst_ids, inst_id or"):
        N.delete_instance({"operator": "admin"})
    mock_im.instance_batch_delete.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_not_found_raises(mock_im):
    mock_im.search_inst.return_value = ([], 0)
    with pytest.raises(ValueError, match="实例不存在"):
        N.delete_instance({"model_id": "host", "inst_name": "ghost"})
    mock_im.instance_batch_delete.assert_not_called()
