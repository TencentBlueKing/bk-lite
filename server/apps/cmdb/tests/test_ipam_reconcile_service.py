"""IPAM 对账登记表模型 + 对账逻辑（本任务先放模型用例，后续任务追加）。"""
import pytest

pytestmark = pytest.mark.django_db


def test_reconcile_source_model_fields():
    from apps.cmdb.models.ipam_models import IPAMReconcileSource
    src = IPAMReconcileSource.objects.create(model_id="host", ip_attr_id="ip_addr", enabled=True)
    assert src.model_id == "host"
    assert src.enabled is True
    assert IPAMReconcileSource.objects.filter(enabled=True).count() == 1


# ---------------------------------------------------------------------------
# Task 6: 纯逻辑测试（无 DB/IO）
# ---------------------------------------------------------------------------

from apps.cmdb.services.ipam_reconcile import match_subnet_for_ip, decide_ip_status


SUBNETS = [
    {"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"},
    {"_id": 2, "subnet_address": "10.0.2.0", "subnet_mask": "24"},
]


class TestMatchSubnet:
    def test_命中唯一子网(self):
        assert match_subnet_for_ip("10.0.1.88", SUBNETS)["_id"] == 1

    def test_无归属返回None(self):
        assert match_subnet_for_ip("192.168.0.1", SUBNETS) is None


class TestDecideStatus:
    def test_单占用者在线(self):
        assert decide_ip_status(["host:5"]) == "online"

    def test_多占用者冲突(self):
        assert decide_ip_status(["host:5", "network:7"]) == "conflict"

    def test_无占用者离线(self):
        assert decide_ip_status([]) == "offline"


# ---------------------------------------------------------------------------
# Task 6: 编排逻辑测试（monkeypatch IO helpers）
# ---------------------------------------------------------------------------


class TestRunReconciliation:
    def test_新IP入账并置在线(self, monkeypatch):
        from apps.cmdb.services import ipam_reconcile
        monkeypatch.setattr(ipam_reconcile, "_load_sources", lambda: [{"model_id": "host", "ip_attr_id": "ip_addr"}])
        monkeypatch.setattr(ipam_reconcile, "_load_subnets", lambda: [{"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"}])
        monkeypatch.setattr(ipam_reconcile, "_load_ci_with_ip",
                            lambda model_id, attr: [{"_id": 55, "model_id": "host", "ip_addr": "10.0.1.10", "inst_name": "h1"}])
        monkeypatch.setattr(ipam_reconcile, "_load_existing_ips", lambda: [])
        created = []
        monkeypatch.setattr(ipam_reconcile, "_upsert_ip_instance",
                            lambda **kw: created.append(kw) or {"_id": 900, **kw})
        monkeypatch.setattr(ipam_reconcile, "_writeback_subnet_utilization", lambda subnet_ids: None)
        result = ipam_reconcile.run_reconciliation()
        assert result["created"] == 1
        assert created[0]["ip_status"] == "online"
        assert created[0]["auto_collect"] is True
        assert created[0]["subnet_id"] == 1

    def test_手工记录不被覆盖(self, monkeypatch):
        from apps.cmdb.services import ipam_reconcile
        monkeypatch.setattr(ipam_reconcile, "_load_sources", lambda: [{"model_id": "host", "ip_attr_id": "ip_addr"}])
        monkeypatch.setattr(ipam_reconcile, "_load_subnets", lambda: [{"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"}])
        monkeypatch.setattr(ipam_reconcile, "_load_ci_with_ip",
                            lambda m, a: [{"_id": 55, "model_id": "host", "ip_addr": "10.0.1.10", "inst_name": "h1"}])
        monkeypatch.setattr(ipam_reconcile, "_load_existing_ips",
                            lambda: [{"_id": 800, "ip_addr": "10.0.1.10", "subnet_id": 1, "auto_collect": False}])
        touched = []
        monkeypatch.setattr(ipam_reconcile, "_upsert_ip_instance", lambda **kw: touched.append(kw))
        monkeypatch.setattr(ipam_reconcile, "_writeback_subnet_utilization", lambda subnet_ids: None)
        result = ipam_reconcile.run_reconciliation()
        assert result["skipped_manual"] == 1
        assert touched == []


class TestEnsureAssociations:
    def test_使用已注册的关联与正确方向(self, monkeypatch):
        """组成边方向必须是 subnet--group-->ip（已注册 subnet_group_ip）；
        ip--connect-->CI。方向错或类型未注册都会被图层拒绝并静默失败。"""
        from apps.cmdb.services import ipam_reconcile
        from apps.cmdb.services.instance import InstanceManage
        captured = []
        monkeypatch.setattr(
            InstanceManage, "instance_association_create",
            staticmethod(lambda data, operator, *a, **k: captured.append(data)),
        )
        ipam_reconcile._ensure_associations(ip_id=900, subnet_id=1, occupants=["host:55"])
        # 组成边：subnet -> ip
        group = [d for d in captured if d["asst_id"] == "group"][0]
        assert group["src_model_id"] == "subnet" and group["dst_model_id"] == "ip"
        assert group["src_inst_id"] == 1 and group["dst_inst_id"] == 900
        assert group["model_asst_id"] == "subnet_group_ip"
        # 关联边：ip -> CI
        conn = [d for d in captured if d["asst_id"] == "connect"][0]
        assert conn["src_model_id"] == "ip" and conn["dst_model_id"] == "host"
        assert conn["model_asst_id"] == "ip_connect_host"
