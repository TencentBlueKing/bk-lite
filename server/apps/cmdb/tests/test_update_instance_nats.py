"""CMDB NATS update_instance 处理器单元测试。

对照 apps/cmdb/nats/nats.py 的 update_instance：实例定位（inst_id / model_id+inst_name）、
参数校验、对 InstanceManage.instance_update 的委托与透传。
"""

from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats as N


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_by_inst_id(mock_im):
    mock_im.instance_update.return_value = {"_id": 123, "inst_name": "host-01"}

    result = N.update_instance(
        {"inst_id": 123, "update_attr": {"ip": "1.2.3.4"}, "operator": "admin"}
    )

    assert result == {"_id": 123, "inst_name": "host-01"}
    mock_im.search_inst.assert_not_called()
    mock_im.instance_update.assert_called_once_with(
        user_groups=[],
        roles=[],
        inst_id=123,
        update_attr={"ip": "1.2.3.4"},
        operator="admin",
        skip_permission_check=True,
    )


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_by_underscore_id(mock_im):
    mock_im.instance_update.return_value = {"_id": 9}

    N.update_instance({"_id": 9, "update_attr": {"k": "v"}})

    _, kwargs = mock_im.instance_update.call_args
    assert kwargs["inst_id"] == 9
    assert kwargs["operator"] == ""


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_by_model_and_name(mock_im):
    mock_im.search_inst.return_value = ([{"_id": 55, "inst_name": "host-01"}], 1)
    mock_im.instance_update.return_value = {"_id": 55}

    N.update_instance(
        {"model_id": "host", "inst_name": "host-01", "update_attr": {"ip": "10.0.0.1"}}
    )

    mock_im.search_inst.assert_called_once_with(model_id="host", inst_name="host-01")
    _, kwargs = mock_im.instance_update.call_args
    assert kwargs["inst_id"] == 55


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_empty_update_attr_raises(mock_im):
    with pytest.raises(ValueError, match="update_attr is required"):
        N.update_instance({"inst_id": 1, "update_attr": {}})
    mock_im.instance_update.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_missing_locator_raises(mock_im):
    with pytest.raises(ValueError, match="inst_id or"):
        N.update_instance({"update_attr": {"k": "v"}})
    mock_im.instance_update.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_update_instance_not_found_raises(mock_im):
    mock_im.search_inst.return_value = ([], 0)
    with pytest.raises(ValueError, match="实例不存在"):
        N.update_instance(
            {"model_id": "host", "inst_name": "ghost", "update_attr": {"k": "v"}}
        )
    mock_im.instance_update.assert_not_called()
