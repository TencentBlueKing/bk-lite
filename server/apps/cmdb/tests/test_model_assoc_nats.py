"""CMDB NATS 模型/分类/关联及单模型实例查询处理器单元测试。

对照 apps/cmdb/nats/nats.py：参数校验、对 ModelManage / ClassificationManage /
InstanceManage 服务方法的委托与透传。
"""

from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats as N


# --------------------------------------------------------------------------
# list_instances
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats._format_asset_instances_response")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_list_instances_ok_formatted(mock_im, mock_fmt):
    mock_im.instance_list.return_value = ([{"_id": 1, "inst_name": "h1"}], 1)
    mock_fmt.return_value = [{"inst_name": "h1", "org": "总部"}]

    result = N.list_instances({"model_id": "host", "page": 2, "page_size": 10, "order": "-inst_name"})

    assert result == {"count": 1, "items": [{"inst_name": "h1", "org": "总部"}]}
    mock_im.instance_list.assert_called_once_with(
        model_id="host",
        params=[],
        page=2,
        page_size=10,
        order="-inst_name",
        creator="",
        permission_map={},
    )
    mock_fmt.assert_called_once_with("host", [{"_id": 1, "inst_name": "h1"}])


@patch("apps.cmdb.nats.nats._format_asset_instances_response")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_list_instances_defaults(mock_im, mock_fmt):
    mock_im.instance_list.return_value = ([], 0)
    mock_fmt.return_value = []

    N.list_instances({"model_id": "host"})

    _, kwargs = mock_im.instance_list.call_args
    assert kwargs["page"] == 1
    assert kwargs["page_size"] == 20
    assert kwargs["order"] == ""


@patch("apps.cmdb.nats.nats._format_asset_instances_response")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_list_instances_no_format(mock_im, mock_fmt):
    mock_im.instance_list.return_value = ([{"_id": 1}], 1)

    result = N.list_instances({"model_id": "host", "format": False})

    assert result == {"count": 1, "items": [{"_id": 1}]}
    mock_fmt.assert_not_called()


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_list_instances_missing_model_id_raises(mock_im):
    with pytest.raises(ValueError, match="model_id is required"):
        N.list_instances({})
    mock_im.instance_list.assert_not_called()


# --------------------------------------------------------------------------
# search_model_attrs
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.ModelManage")
def test_search_model_attrs_ok(mock_mm):
    mock_mm.search_model_attr.return_value = [{"attr_id": "ip"}]

    assert N.search_model_attrs({"model_id": "host"}) == [{"attr_id": "ip"}]
    mock_mm.search_model_attr.assert_called_once_with("host")


@patch("apps.cmdb.nats.nats.ModelManage")
def test_search_model_attrs_missing_model_id_raises(mock_mm):
    with pytest.raises(ValueError, match="model_id is required"):
        N.search_model_attrs({})
    mock_mm.search_model_attr.assert_not_called()


# --------------------------------------------------------------------------
# search_models
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.ModelManage")
def test_search_models_all(mock_mm):
    mock_mm.search_model.return_value = [{"model_id": "host"}]

    assert N.search_models() == [{"model_id": "host"}]
    mock_mm.search_model.assert_called_once_with(classification_ids=None, include_hidden=False)


@patch("apps.cmdb.nats.nats.ModelManage")
def test_search_models_by_classification(mock_mm):
    mock_mm.search_model.return_value = []

    N.search_models({"classification_id": "host_mgmt", "include_hidden": True})

    mock_mm.search_model.assert_called_once_with(classification_ids=["host_mgmt"], include_hidden=True)


# --------------------------------------------------------------------------
# search_classifications
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.ClassificationManage")
def test_search_classifications_ok(mock_cm):
    mock_cm.search_model_classification.return_value = [{"classification_id": "c1"}]

    assert N.search_classifications() == [{"classification_id": "c1"}]
    mock_cm.search_model_classification.assert_called_once_with(include_hidden=False)


# --------------------------------------------------------------------------
# search_model_associations
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.ModelManage")
def test_search_model_associations_ok(mock_mm):
    mock_mm.model_association_search.return_value = [{"model_asst_id": "a1"}]

    assert N.search_model_associations({"model_id": "host"}) == [{"model_asst_id": "a1"}]
    mock_mm.model_association_search.assert_called_once_with("host")


@patch("apps.cmdb.nats.nats.ModelManage")
def test_search_model_associations_missing_model_id_raises(mock_mm):
    with pytest.raises(ValueError, match="model_id is required"):
        N.search_model_associations({})
    mock_mm.model_association_search.assert_not_called()


# --------------------------------------------------------------------------
# search_instance_associations
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_search_instance_associations_ok(mock_im):
    mock_im.instance_association_instance_list.return_value = [{"model_asst_id": "a1", "inst_list": []}]

    result = N.search_instance_associations({"model_id": "host", "inst_id": "12"})

    assert result == [{"model_asst_id": "a1", "inst_list": []}]
    mock_im.instance_association_instance_list.assert_called_once_with("host", 12)


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_search_instance_associations_missing_args_raises(mock_im):
    with pytest.raises(ValueError, match="model_id and inst_id are required"):
        N.search_instance_associations({"model_id": "host"})
    mock_im.instance_association_instance_list.assert_not_called()


# --------------------------------------------------------------------------
# create_instance_association
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_association_ok(mock_im):
    mock_im.instance_association_create.return_value = {"_id": 100}

    result = N.create_instance_association(
        {
            "src_inst_id": "1",
            "dst_inst_id": "2",
            "model_asst_id": "host_run_app",
            "asst_id": "run",
            "operator": "admin",
        }
    )

    assert result == {"_id": 100}
    mock_im.instance_association_create.assert_called_once_with(
        {
            "src_inst_id": 1,
            "dst_inst_id": 2,
            "model_asst_id": "host_run_app",
            "asst_id": "run",
        },
        "admin",
    )


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_association_default_operator(mock_im):
    mock_im.instance_association_create.return_value = {"_id": 1}

    N.create_instance_association({"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "a"})

    args, _ = mock_im.instance_association_create.call_args
    assert args[1] == ""


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_instance_association_missing_args_raises(mock_im):
    with pytest.raises(ValueError, match="src_inst_id, dst_inst_id and model_asst_id are required"):
        N.create_instance_association({"src_inst_id": 1, "dst_inst_id": 2})
    mock_im.instance_association_create.assert_not_called()


# --------------------------------------------------------------------------
# delete_instance_association
# --------------------------------------------------------------------------


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_association_ok(mock_im):
    result = N.delete_instance_association({"asso_id": "10", "operator": "admin"})

    assert result == {"result": True, "deleted": 10}
    mock_im.instance_association_delete.assert_called_once_with(10, "admin")


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_association_compat_keys(mock_im):
    N.delete_instance_association({"inst_asst_id": 7})
    mock_im.instance_association_delete.assert_called_once_with(7, "")


@patch("apps.cmdb.nats.nats.InstanceManage")
def test_delete_instance_association_missing_id_raises(mock_im):
    with pytest.raises(ValueError, match="asso_id is required"):
        N.delete_instance_association({"operator": "admin"})
    mock_im.instance_association_delete.assert_not_called()
