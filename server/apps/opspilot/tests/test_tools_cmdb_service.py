"""CMDB @tool 单元测试 (cmdb/instances, associations, search, models)。

用真实 DB User 走 _get_user_from_config 的真实 ORM 查询路径,只 mock CMDB 服务边界
(InstanceManage / ModelManage)与权限映射/校验辅助(build_permission_map /
ensure_*_permission,内部依赖 cmdb 权限规则基础设施)。断言成功包装结构、入参契约
(校验/类型错误)、write 守卫(allow_write/superuser)、not-found 路径与异常被
wrap_error 捕获。不连真实图数据库。
"""

from unittest.mock import patch

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.metis.llm.tools.cmdb import associations as assoc
from apps.opspilot.metis.llm.tools.cmdb import instances as inst
from apps.opspilot.metis.llm.tools.cmdb import models as mdl
from apps.opspilot.metis.llm.tools.cmdb import search as srch


@pytest.fixture
def user(db):
    from apps.base.models import User

    return User.objects.create_user(
        username="cmdbuser",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T"}],
        roles=["admin"],
    )


@pytest.fixture
def super_user(db):
    from apps.base.models import User

    u = User.objects.create_user(
        username="cmdbsuper",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T"}],
        roles=["admin"],
    )
    u.is_superuser = True
    u.save()
    return u


def cfg(uid, **extra):
    base = {"user_id": uid}
    base.update(extra)
    return {"configurable": base}


# ----------------- instances -----------------
class TestSearchInstances:
    def test_success(self, user):
        with patch.object(inst, "build_permission_map", return_value={}), patch.object(
            inst.InstanceManage,
            "instance_list",
            return_value=([{"_id": 1, "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "inst_name": "h"}], 1),
        ) as m:
            out = inst.cmdb_search_instances.func(
                **{"model_id": "host", "query_list": [{"field": "a", "type": "str=", "value": "v"}], "config": cfg(user.id)}
            )
        assert out["success"] is True
        assert out["data"]["count"] == 1
        assert out["data"]["insts"] == [{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "inst_name": "h"}]
        # query_list 经 normalize 后透传
        assert m.call_args.kwargs["params"] == [{"field": "a", "type": "str=", "value": "v"}]
        assert m.call_args.kwargs["creator"] == "cmdbuser"

    def test_missing_model_id(self, user):
        out = inst.cmdb_search_instances.func(**{"model_id": "", "config": cfg(user.id)})
        assert out["success"] is False
        assert "model_id is required" in out["error"]

    def test_missing_user_id_in_config(self):
        out = inst.cmdb_search_instances.func(**{"model_id": "host", "config": {}})
        assert out["success"] is False
        assert "user_id is required" in out["error"]

    def test_user_not_found(self, db):
        out = inst.cmdb_search_instances.func(**{"model_id": "host", "config": cfg(999999)})
        assert out["success"] is False
        assert "user_id not found" in out["error"]


class TestGetInstance:
    def test_success(self, user):
        with patch.object(
            inst.InstanceManage,
            "query_entity_by_uuid",
            return_value={"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "model_id": "host", "inst_name": "h"},
        ), patch.object(inst, "build_permission_map", return_value={}), patch.object(inst, "ensure_instance_permission", return_value=None):
            out = inst.cmdb_get_instance.func(**{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)})
        assert out["data"]["inst_uuid"] == "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
        assert "_id" not in out["data"]

    def test_not_found(self, user):
        with patch.object(inst.InstanceManage, "query_entity_by_uuid", return_value=None):
            out = inst.cmdb_get_instance.func(**{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)})
        assert "instance not found" in out["error"]


class TestCreateInstance:
    def test_write_disabled(self, user):
        out = inst.cmdb_create_instance.func(**{"model_id": "host", "instance_info": {"ip": "1.1.1.1"}, "allow_write": False, "config": cfg(user.id)})
        assert "allow_write=false" in out["error"]

    def test_non_superuser_blocked(self, user):
        out = inst.cmdb_create_instance.func(**{"model_id": "host", "instance_info": {"ip": "1"}, "allow_write": True, "config": cfg(user.id)})
        assert "superuser" in out["error"]

    def test_bad_instance_info_type(self, super_user):
        out = inst.cmdb_create_instance.func(**{"model_id": "host", "instance_info": "notadict", "allow_write": True, "config": cfg(super_user.id)})
        assert "must be a dict" in out["error"]

    def test_superuser_success_non_children(self, super_user):
        with patch.object(inst.InstanceManage, "instance_create", return_value={"_id": 9}) as m:
            out = inst.cmdb_create_instance.func(
                **{"model_id": "host", "instance_info": {"ip": "1"}, "allow_write": True, "team_id": 1, "config": cfg(super_user.id)}
            )
        assert out["data"] == {"_id": 9}
        # superuser non-children -> allowed_org_ids = [team]
        from apps.system_mgmt.utils.group_utils import GroupUtils  # noqa

        assert m.call_args.kwargs["allowed_org_ids"] == [1]

    def test_superuser_success_with_children(self, super_user):
        with patch.object(inst.InstanceManage, "instance_create", return_value={"_id": 4}) as m, patch.object(
            inst.GroupUtils, "get_group_with_descendants", return_value=[1, 2, 3]
        ):
            out = inst.cmdb_create_instance.func(
                **{
                    "model_id": "host",
                    "instance_info": {"ip": "1"},
                    "allow_write": True,
                    "team_id": 1,
                    "include_children": True,
                    "config": cfg(super_user.id),
                }
            )
        assert out["data"] == {"_id": 4}
        # superuser + children -> descendants used as allowed_org_ids
        assert m.call_args.kwargs["allowed_org_ids"] == [1, 2, 3]


class TestUpdateDeleteInstance:
    def test_update_success(self, super_user):
        with patch.object(inst, "build_user_groups", return_value=[{"id": 1}]), patch.object(
            inst.InstanceManage, "instance_update_by_uuid", return_value={"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "inst_name": "n"}
        ) as m:
            out = inst.cmdb_update_instance.func(
                **{
                    "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
                    "update_data": {"name": "n"},
                    "allow_write": True,
                    "config": cfg(super_user.id),
                }
            )
        assert out["data"]["inst_uuid"] == "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
        assert "_id" not in out["data"]
        assert m.call_args[0][1] == super_user.roles

    def test_update_bad_data_type(self, super_user):
        out = inst.cmdb_update_instance.func(
            **{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "update_data": "x", "allow_write": True, "config": cfg(super_user.id)}
        )
        assert "must be a dict" in out["error"]

    def test_batch_update_empty_ids(self, super_user):
        out = inst.cmdb_batch_update_instances.func(**{"inst_uuids": [], "update_data": {"a": 1}, "allow_write": True, "config": cfg(super_user.id)})
        assert "inst_uuids is required" in out["error"]

    def test_batch_update_success(self, super_user):
        with patch.object(inst, "build_user_groups", return_value=[{"id": 1}]), patch.object(
            inst.InstanceManage,
            "batch_instance_update_by_uuids",
            return_value=[{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"}, {"inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb"}],
        ):
            out = inst.cmdb_batch_update_instances.func(
                **{
                    "inst_uuids": ["63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "c28e467a-501d-426f-a3c3-6e560c7b33cb"],
                    "update_data": {"a": 1},
                    "allow_write": True,
                    "config": cfg(super_user.id),
                }
            )
        assert len(out["data"]) == 2

    def test_delete_success(self, super_user):
        with patch.object(inst, "build_user_groups", return_value=[{"id": 1}]), patch.object(
            inst.InstanceManage, "instance_batch_delete_by_uuids", return_value=None
        ):
            out = inst.cmdb_delete_instance.func(
                **{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "allow_write": True, "config": cfg(super_user.id)}
            )
        assert out["data"] == {"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "deleted": True}

    def test_batch_delete_empty(self, super_user):
        out = inst.cmdb_batch_delete_instances.func(**{"inst_uuids": [], "allow_write": True, "config": cfg(super_user.id)})
        assert "inst_uuids is required" in out["error"]

    def test_batch_delete_success(self, super_user):
        with patch.object(inst, "build_user_groups", return_value=[{"id": 1}]), patch.object(
            inst.InstanceManage, "instance_batch_delete_by_uuids", return_value=None
        ) as m:
            out = inst.cmdb_batch_delete_instances.func(
                **{
                    "inst_uuids": ["63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "c28e467a-501d-426f-a3c3-6e560c7b33cb"],
                    "allow_write": True,
                    "config": cfg(super_user.id),
                }
            )
        assert out["data"]["deleted"] is True
        assert m.call_args[0][2] == ["63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "c28e467a-501d-426f-a3c3-6e560c7b33cb"]


class TestTopo:
    def test_topo_search_success(self, user):
        with patch.object(
            inst.InstanceManage, "query_entity_by_uuid", return_value={"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "model_id": "host"}
        ), patch.object(inst, "build_permission_map", return_value={}), patch.object(
            inst, "ensure_instance_permission", return_value=None
        ), patch.object(
            inst.InstanceManage, "topo_search_lite_by_uuid", return_value={"nodes": []}
        ):
            out = inst.cmdb_topo_search.func(**{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)})
        assert out["data"] == {"nodes": []}

    def test_topo_search_not_found(self, user):
        with patch.object(inst.InstanceManage, "query_entity_by_uuid", return_value=None):
            out = inst.cmdb_topo_search.func(**{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)})
        assert "instance not found" in out["error"]

    def test_topo_expand_bad_parent_ids(self, user):
        out = inst.cmdb_topo_expand.func(**{"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "parent_uuids": "x", "config": cfg(user.id)})
        assert "parent_uuids must be a list" in out["error"]

    def test_topo_expand_success(self, user):
        with patch.object(
            inst.InstanceManage, "query_entity_by_uuid", return_value={"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "model_id": "host"}
        ), patch.object(inst, "build_permission_map", return_value={}), patch.object(
            inst, "ensure_instance_permission", return_value=None
        ), patch.object(
            inst.InstanceManage, "topo_search_expand_by_uuid", return_value={"expanded": True}
        ):
            out = inst.cmdb_topo_expand.func(
                **{
                    "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
                    "parent_uuids": ["c28e467a-501d-426f-a3c3-6e560c7b33cb"],
                    "config": cfg(user.id),
                }
            )
        assert out["data"] == {"expanded": True}


# ----------------- associations -----------------
class TestAssociations:
    def test_list_model_assoc_success(self, user):
        with patch.object(assoc.ModelManage, "search_model_info", return_value={"model_id": "host"}), patch.object(
            assoc, "build_permission_map", return_value={}
        ), patch.object(assoc, "ensure_model_permission", return_value=None), patch.object(
            assoc.ModelManage, "model_association_search", return_value=[{"asst_id": "run"}]
        ):
            out = assoc.cmdb_list_model_associations.func(**{"model_id": "host", "config": cfg(user.id)})
        assert out["data"] == [{"asst_id": "run"}]

    def test_list_model_assoc_model_missing(self, user):
        out = assoc.cmdb_list_model_associations.func(**{"model_id": "", "config": cfg(user.id)})
        assert "model_id is required" in out["error"]

    def test_list_model_assoc_not_found(self, user):
        with patch.object(assoc.ModelManage, "search_model_info", return_value=None):
            out = assoc.cmdb_list_model_associations.func(**{"model_id": "host", "config": cfg(user.id)})
        assert "model not found" in out["error"]

    def test_list_instance_assoc_success(self, user):
        with patch.object(
            assoc.InstanceManage, "query_entity_by_uuid", return_value={"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "model_id": "host"}
        ), patch.object(assoc, "build_permission_map", return_value={}), patch.object(
            assoc, "ensure_instance_permission", return_value=None
        ), patch.object(
            assoc.InstanceManage,
            "instance_association_instance_list_by_uuid",
            return_value=[{"dst_inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb"}],
        ):
            out = assoc.cmdb_list_instance_associations.func(
                **{"model_id": "host", "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)}
            )
        assert out["data"] == [{"dst_inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb"}]

    def test_list_instance_assoc_inst_not_found(self, user):
        with patch.object(assoc.InstanceManage, "query_entity_by_uuid", return_value=None):
            out = assoc.cmdb_list_instance_associations.func(
                **{"model_id": "host", "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)}
            )
        assert "instance not found" in out["error"]

    def test_list_associated_instances_success(self, user):
        with patch.object(
            assoc.InstanceManage, "query_entity_by_uuid", return_value={"inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "model_id": "host"}
        ), patch.object(assoc, "build_permission_map", return_value={}), patch.object(
            assoc, "ensure_instance_permission", return_value=None
        ), patch.object(
            assoc.InstanceManage, "instance_association_instance_list_by_uuid", return_value=[{"inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb"}]
        ):
            out = assoc.cmdb_list_associated_instances.func(
                **{"model_id": "host", "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "config": cfg(user.id)}
            )
        assert out["data"] == [{"inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb"}]

    def test_create_assoc_write_disabled(self, user):
        out = assoc.cmdb_create_instance_association.func(**{"data": {"a": 1}, "allow_write": False, "config": cfg(user.id)})
        assert "allow_write=false" in out["error"]

    def test_create_assoc_bad_data(self, super_user):
        out = assoc.cmdb_create_instance_association.func(**{"data": "x", "allow_write": True, "config": cfg(super_user.id)})
        assert "must be a dict" in out["error"]

    def test_create_assoc_success(self, super_user):
        with patch.object(assoc.InstanceManage, "instance_association_create_by_uuid", return_value={"model_asst_id": "host_run_host"}) as m:
            out = assoc.cmdb_create_instance_association.func(
                **{
                    "data": {
                        "src_inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
                        "dst_inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb",
                        "model_asst_id": "host_run_host",
                    },
                    "allow_write": True,
                    "config": cfg(super_user.id),
                }
            )
        assert out["data"] == {"model_asst_id": "host_run_host"}
        assert m.call_args.kwargs["operator"] == "cmdbsuper"

    def test_delete_assoc_success(self, super_user):
        with patch.object(assoc.InstanceManage, "instance_association_delete_by_key", return_value={"deleted": True}):
            out = assoc.cmdb_delete_instance_association.func(
                **{
                    "src_inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
                    "dst_inst_uuid": "c28e467a-501d-426f-a3c3-6e560c7b33cb",
                    "model_asst_id": "host_run_host",
                    "allow_write": True,
                    "config": cfg(super_user.id),
                }
            )
        assert out["data"]["deleted"] is True


# ----------------- search -----------------
class TestSearch:
    def test_fulltext_success(self, user):
        with patch.object(srch, "build_permission_map", return_value={}), patch.object(
            srch.InstanceManage, "fulltext_search", return_value=[{"_id": 1}]
        ):
            out = srch.cmdb_fulltext_search.func(**{"search": "web", "config": cfg(user.id)})
        assert out["data"] == [{"_id": 1}]

    def test_fulltext_empty_search(self, user):
        out = srch.cmdb_fulltext_search.func(**{"search": "", "config": cfg(user.id)})
        assert "search is required" in out["error"]

    def test_fulltext_stats_success(self, user):
        with patch.object(srch, "build_permission_map", return_value={}), patch.object(
            srch.InstanceManage, "fulltext_search_stats", return_value={"host": 3}
        ):
            out = srch.cmdb_fulltext_search_stats.func(**{"search": "web", "config": cfg(user.id)})
        assert out["data"] == {"host": 3}

    def test_fulltext_stats_empty(self, user):
        out = srch.cmdb_fulltext_search_stats.func(**{"search": "", "config": cfg(user.id)})
        assert "search is required" in out["error"]

    def test_fulltext_by_model_success(self, user):
        with patch.object(srch, "build_permission_map", return_value={}), patch.object(
            srch.InstanceManage, "fulltext_search_by_model", return_value={"insts": [], "count": 0}
        ) as m:
            out = srch.cmdb_fulltext_search_by_model.func(**{"search": "web", "model_id": "host", "page": 2, "page_size": 5, "config": cfg(user.id)})
        assert out["data"]["count"] == 0
        assert m.call_args.kwargs["page"] == 2
        assert m.call_args.kwargs["page_size"] == 5

    def test_fulltext_by_model_missing_model(self, user):
        out = srch.cmdb_fulltext_search_by_model.func(**{"search": "x", "model_id": "", "config": cfg(user.id)})
        assert "model_id is required" in out["error"]


# ----------------- models -----------------
class TestModels:
    def test_list_models_grouping(self, user):
        models = [
            {"classification_id": "net", "model_id": "switch", "model_name": "交换机"},
            {"classification_id": "net", "model_id": "router", "model_name": "路由器"},
            {"classification_id": "", "model_id": "skip", "model_name": "x"},  # no cat
        ]
        with patch.object(mdl, "build_permission_map", return_value={}), patch.object(mdl.ModelManage, "search_model", return_value=models):
            out = mdl.cmdb_list_models.func(**{"config": cfg(user.id)})
        cats = out["data"]["model_categories"]
        assert len(cats) == 1
        assert cats[0]["category"] == "net"
        assert {m["id"] for m in cats[0]["models"]} == {"switch", "router"}

    def test_get_model_info_success(self, user):
        with patch.object(mdl.ModelManage, "search_model_info", return_value={"model_id": "host", "model_name": "主机"}), patch.object(
            mdl, "build_permission_map", return_value={}
        ), patch.object(mdl, "ensure_model_permission", return_value=None):
            out = mdl.cmdb_get_model_info.func(**{"model_id": "host", "config": cfg(user.id)})
        assert out["data"]["model_name"] == "主机"

    def test_get_model_info_missing(self, user):
        out = mdl.cmdb_get_model_info.func(**{"model_id": "", "config": cfg(user.id)})
        assert "model_id is required" in out["error"]

    def test_get_model_info_not_found(self, user):
        with patch.object(mdl.ModelManage, "search_model_info", return_value=None):
            out = mdl.cmdb_get_model_info.func(**{"model_id": "host", "config": cfg(user.id)})
        assert "model not found" in out["error"]

    def test_list_model_attrs_filters_display_field(self, user):
        attrs = [
            {"attr_id": "name", "is_display_field": True},
            {"attr_id": "ip", "is_display_field": False},
            {"attr_id": "os"},
        ]
        with patch.object(mdl.ModelManage, "search_model_info", return_value={"model_id": "host"}), patch.object(
            mdl, "build_permission_map", return_value={}
        ), patch.object(mdl, "ensure_model_permission", return_value=None), patch.object(mdl.ModelManage, "search_model_attr", return_value=attrs):
            out = mdl.cmdb_list_model_attrs.func(**{"model_id": "host", "config": cfg(user.id)})
        ids = {a["attr_id"] for a in out["data"]}
        assert ids == {"ip", "os"}  # display field filtered out

    def test_list_model_attrs_not_found(self, user):
        with patch.object(mdl.ModelManage, "search_model_info", return_value=None):
            out = mdl.cmdb_list_model_attrs.func(**{"model_id": "host", "config": cfg(user.id)})
        assert "model not found" in out["error"]
