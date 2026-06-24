"""ipam_init 幂等：补齐子网新字段 + ip 描述 + ip--use-->host/network 关联 + 登记表种子。规格 §2/§5.1。"""
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.django_db


def test_ipam_init_adds_missing_subnet_attrs_and_seeds_sources():
    from apps.cmdb.management.commands.ipam_init import run_ipam_init
    from apps.cmdb.models.ipam_models import IPAMReconcileSource
    with patch("apps.cmdb.management.commands.ipam_init.ModelManage.search_model_attr",
               return_value=[{"attr_id": "inst_name"}]), \
         patch("apps.cmdb.management.commands.ipam_init.ModelManage.create_model_attr") as mk_attr, \
         patch("apps.cmdb.management.commands.ipam_init._ensure_association") as mk_assoc:
        run_ipam_init()
    created_ids = set()
    for c in mk_attr.call_args_list:
        # create_model_attr(model_id, attr_info, ...) -> attr_info is 2nd positional or kwarg
        attr_info = c.args[1] if len(c.args) > 1 else c.kwargs.get("attr_info")
        created_ids.add(attr_info["attr_id"])
    assert {"gateway", "vlan_id", "usage_type", "owner"}.issubset(created_ids)
    # ip 模型新增：描述 + 三个枚举 + 使用人（PRD 误称"已有"，实际 attr-ip 里没有）
    assert {"description", "ip_status", "ip_allocated_status", "ip_type", "ip_user"}.issubset(created_ids)
    assert IPAMReconcileSource.objects.filter(model_id="host", ip_attr_id="ip_addr").exists()
    assert IPAMReconcileSource.objects.filter(model_id="network", ip_attr_id="ip").exists()


def test_ipam_init_ip_status_enum_defaults_unknown():
    """ip_status 枚举默认值为 unknown（规格 §2.2：现网状态默认未知）。"""
    from apps.cmdb.management.commands.ipam_init import IP_NEW_ATTRS
    by_id = {a["attr_id"]: a for a in IP_NEW_ATTRS}
    assert by_id["ip_status"]["attr_type"] == "enum"
    assert {o["id"] for o in by_id["ip_status"]["option"]} == {"online", "offline", "conflict", "unknown"}
    assert by_id["ip_status"].get("default_value") == ["unknown"]
    assert {o["id"] for o in by_id["ip_allocated_status"]["option"]} == {"available", "allocated", "reserved"}
    assert {o["id"] for o in by_id["ip_type"]["option"]} == {"static", "dynamic", "float", "gateway", "reserved"}


def test_ipam_init_is_idempotent_on_existing_attrs():
    from apps.cmdb.management.commands.ipam_init import run_ipam_init
    existing = [{"attr_id": a} for a in
                ["inst_name", "gateway", "vlan_id", "usage_type", "owner",
                 "description", "ip_status", "ip_allocated_status", "ip_type", "ip_user"]]
    with patch("apps.cmdb.management.commands.ipam_init.ModelManage.search_model_attr", return_value=existing), \
         patch("apps.cmdb.management.commands.ipam_init.ModelManage.create_model_attr") as mk_attr, \
         patch("apps.cmdb.management.commands.ipam_init._ensure_association"):
        run_ipam_init()
    mk_attr.assert_not_called()


def test_ipam_init_uses_registered_connect_assoc_type():
    """IP↔CI 关联用已注册的 connect 类型（use 未注册会静默失败）。"""
    from apps.cmdb.management.commands import ipam_init
    calls = []
    with patch.object(ipam_init, "_ensure_attrs"), \
         patch.object(ipam_init, "_ensure_association", side_effect=lambda *a: calls.append(a)), \
         patch.object(ipam_init, "_seed_sources"):
        ipam_init.run_ipam_init()
    assert ("ip", "host", "connect") in calls
    assert ("ip", "network", "connect") in calls
