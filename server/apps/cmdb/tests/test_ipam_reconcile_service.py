"""IPAM 对账登记表模型 + 对账逻辑（本任务先放模型用例，后续任务追加）。"""
import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


def test_reconcile_source_model_fields():
    from apps.cmdb.models.ipam_models import IPAMReconcileSource
    # 用非默认种子的来源，避免与数据迁移 0029 预置的 host.ip_addr/network.ip 撞唯一键
    src = IPAMReconcileSource.objects.create(model_id="switch", ip_attr_id="mgmt_ip", enabled=True)
    assert src.model_id == "switch"
    assert src.enabled is True
    assert IPAMReconcileSource.objects.filter(model_id="switch", ip_attr_id="mgmt_ip").exists()


def test_seed_reconcile_sources_idempotent():
    """seed_reconcile_sources 预置 host.ip_addr / network.ip，且可重复执行不重复插入。
    数据迁移与（如有）init 流程共用此函数；替代被删除的 ipam_init 命令。"""
    from apps.cmdb.models.ipam_models import IPAMReconcileSource, seed_reconcile_sources
    seed_reconcile_sources(IPAMReconcileSource)
    assert IPAMReconcileSource.objects.filter(model_id="host", ip_attr_id="ip_addr").exists()
    assert IPAMReconcileSource.objects.filter(model_id="network", ip_attr_id="ip").exists()
    n = IPAMReconcileSource.objects.count()
    seed_reconcile_sources(IPAMReconcileSource)  # 幂等
    assert IPAMReconcileSource.objects.count() == n


# ---------------------------------------------------------------------------
# Task 6: 纯逻辑测试（无 DB/IO）
# ---------------------------------------------------------------------------

from apps.cmdb.services.ipam_reconcile import match_subnet_for_ip, decide_ip_status


SUBNETS = [
    {"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"},
    {"_id": 2, "subnet_address": "10.0.2.0", "subnet_mask": "24"},
]


def test_ci_source_is_loaded_by_stable_id_cursor_batches(monkeypatch):
    from apps.cmdb.services import ipam_reconcile

    calls = []

    class FakeGraph:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def query_entity(self, label, params, **kwargs):
            calls.append((params, kwargs))
            cursor = next((item["value"] for item in params if item["type"] == "id>"), 0)
            rows = {
                0: [{"_id": 1, "ip_addr": "10.0.1.1"}, {"_id": 2, "ip_addr": "10.0.1.2"}],
                2: [{"_id": 5, "ip_addr": "10.0.1.5"}],
            }[cursor]
            return rows, None

    monkeypatch.setattr(ipam_reconcile, "GraphClient", FakeGraph)

    rows = list(ipam_reconcile._load_ci_with_ip("host", "ip_addr", batch_size=2))

    assert [row["_id"] for row in rows] == [1, 2, 5]
    assert len(calls) == 2
    assert calls[0][1] == {"page": {"skip": 0, "limit": 2}, "include_count": False}
    assert calls[1][0][-1] == {"field": "id", "type": "id>", "value": 2}


def test_existing_ip_reference_set_fails_closed_above_limit(monkeypatch):
    from apps.cmdb.services import ipam_reconcile

    class FakeGraph:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def query_entity(self, label, params, **kwargs):
            assert kwargs == {"page": {"skip": 0, "limit": 3}, "include_count": False}
            return [{"_id": 1}, {"_id": 2}, {"_id": 3}], None

    monkeypatch.setattr(ipam_reconcile, "GraphClient", FakeGraph)

    with pytest.raises(ipam_reconcile.IPAMReconcileLimitExceeded, match="existing_ips.*2"):
        ipam_reconcile._load_existing_ips(limit=2)


@override_settings(IPAM_RECONCILE_OCCUPANT_LIMIT=1)
def test_occupant_aggregation_fails_closed_above_limit(monkeypatch):
    from apps.cmdb.services import ipam_reconcile

    monkeypatch.setattr(ipam_reconcile, "_load_sources", lambda: [{"model_id": "host", "ip_attr_id": "ip_addr"}])
    monkeypatch.setattr(
        ipam_reconcile,
        "_load_subnets",
        lambda: [{"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"}],
    )
    monkeypatch.setattr(ipam_reconcile, "_load_existing_ips", lambda: [])
    monkeypatch.setattr(
        ipam_reconcile,
        "_load_ci_with_ip",
        lambda *args: [
            {"_id": 1, "model_id": "host", "ip_addr": "10.0.1.1"},
            {"_id": 2, "model_id": "host", "ip_addr": "10.0.1.2"},
        ],
    )

    with pytest.raises(ipam_reconcile.IPAMReconcileLimitExceeded, match="occupants.*1"):
        ipam_reconcile.run_reconciliation()


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

    def test_auto_collect缺失的记录也按手工保护(self, monkeypatch):
        """非自动创建的记录（auto_collect 缺失/None，如手工经通用表单建的）也不能被对账覆盖。
        仅 auto_collect is True 才是对账自己的记录、可写。"""
        from apps.cmdb.services import ipam_reconcile
        monkeypatch.setattr(ipam_reconcile, "_load_sources", lambda: [{"model_id": "host", "ip_attr_id": "ip_addr"}])
        monkeypatch.setattr(ipam_reconcile, "_load_subnets", lambda: [{"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"}])
        monkeypatch.setattr(ipam_reconcile, "_load_ci_with_ip",
                            lambda m, a: [{"_id": 55, "model_id": "host", "ip_addr": "10.0.1.10", "inst_name": "h1"}])
        # 已有记录没有 auto_collect 字段（None）
        monkeypatch.setattr(ipam_reconcile, "_load_existing_ips",
                            lambda: [{"_id": 801, "ip_addr": "10.0.1.10", "subnet_id": "1"}])
        touched = []
        monkeypatch.setattr(ipam_reconcile, "_upsert_ip_instance", lambda **kw: touched.append(kw))
        monkeypatch.setattr(ipam_reconcile, "_writeback_subnet_utilization", lambda subnet_ids: None)
        result = ipam_reconcile.run_reconciliation()
        assert result["skipped_manual"] == 1
        assert touched == []

    def test_自动发现IP本轮无CI命中则置离线(self, monkeypatch):
        """auto_collect=True 但本轮无任何 CI 命中的 IP → 置 offline（台账跟随 CI 变更，§2.4）。
        手工记录(auto_collect 非 True)即使无命中也不动。"""
        from apps.cmdb.services import ipam_reconcile
        monkeypatch.setattr(ipam_reconcile, "_load_sources", lambda: [{"model_id": "host", "ip_attr_id": "ip_addr"}])
        monkeypatch.setattr(ipam_reconcile, "_load_subnets", lambda: [{"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"}])
        monkeypatch.setattr(ipam_reconcile, "_load_ci_with_ip",
                            lambda m, a: [{"_id": 55, "model_id": "host", "ip_addr": "10.0.1.10", "inst_name": "h1"}])
        # .10 自动且本轮命中(保持)、.99 自动但本轮无命中(→离线)、.30 手工无命中(不动)
        monkeypatch.setattr(ipam_reconcile, "_load_existing_ips", lambda: [
            {"_id": 901, "ip_addr": "10.0.1.10", "subnet_id": "1", "auto_collect": True},
            {"_id": 902, "ip_addr": "10.0.1.99", "subnet_id": "1", "auto_collect": True},
            {"_id": 903, "ip_addr": "10.0.1.30", "subnet_id": "1", "auto_collect": False},
        ])
        monkeypatch.setattr(ipam_reconcile, "_upsert_ip_instance", lambda **kw: {"_id": 900, **kw})
        offs = []
        monkeypatch.setattr(ipam_reconcile, "_mark_offline", lambda ip_id: offs.append(ip_id))
        monkeypatch.setattr(ipam_reconcile, "_writeback_subnet_utilization", lambda s: None)
        result = ipam_reconcile.run_reconciliation()
        assert offs == [902]
        assert result["offline"] == 1


# ---------------------------------------------------------------------------
# DEFECT B (reconcile side) — _upsert_ip_instance must write collect_time
# ---------------------------------------------------------------------------

class TestUpsertIpInstanceCollectTime:
    """DEFECT B: _upsert_ip_instance payload must include collect_time."""

    def test_collect_time_in_payload(self, monkeypatch):
        from apps.cmdb.services import ipam_reconcile
        from apps.cmdb.services.instance import InstanceManage

        captured_payloads = []

        def fake_instance_create(model_id, payload, operator, **kw):
            captured_payloads.append(payload)
            return {"_id": 888}

        monkeypatch.setattr(InstanceManage, "instance_create", staticmethod(fake_instance_create))
        monkeypatch.setattr(ipam_reconcile, "_ensure_associations", lambda *a, **k: None)

        ipam_reconcile._upsert_ip_instance(
            existing_id=None,
            subnet_id=1,
            ip_addr="10.0.1.5",
            ip_status="online",
            auto_collect=True,
            occupants=[],
            organization=[1],
        )

        assert len(captured_payloads) == 1
        assert "collect_time" in captured_payloads[0]
        assert captured_payloads[0]["collect_time"]  # non-empty


# ---------------------------------------------------------------------------
# DEFECT C — run_reconciliation must add subnet to affected_subnets even for
# manual-skipped IPs so utilization is always recomputed
# ---------------------------------------------------------------------------

class TestReconciliationManualSkipSubnetWriteback:
    """DEFECT C: when a matched IP is manual-protected, the subnet must still
    appear in the _writeback_subnet_utilization call."""

    def test_manual_skip_subnet_still_written_back(self, monkeypatch):
        from apps.cmdb.services import ipam_reconcile

        monkeypatch.setattr(ipam_reconcile, "_load_sources",
                            lambda: [{"model_id": "host", "ip_attr_id": "ip_addr"}])
        monkeypatch.setattr(ipam_reconcile, "_load_subnets",
                            lambda: [{"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24"}])
        monkeypatch.setattr(ipam_reconcile, "_load_ci_with_ip",
                            lambda m, a: [{"_id": 55, "model_id": "host", "ip_addr": "10.0.1.10", "inst_name": "h1"}])
        # existing IP is manual (auto_collect=False)
        monkeypatch.setattr(ipam_reconcile, "_load_existing_ips",
                            lambda: [{"_id": 800, "ip_addr": "10.0.1.10", "subnet_id": "1", "auto_collect": False}])

        touched = []
        monkeypatch.setattr(ipam_reconcile, "_upsert_ip_instance", lambda **kw: touched.append(kw))

        writeback_args = []
        monkeypatch.setattr(ipam_reconcile, "_writeback_subnet_utilization",
                            lambda subnet_ids: writeback_args.append(set(subnet_ids)))

        result = ipam_reconcile.run_reconciliation()

        # manual-skip counter correct
        assert result["skipped_manual"] == 1
        # _upsert_ip_instance must NOT be called
        assert touched == []
        # subnet 1 MUST appear in writeback (currently failing — the bug)
        assert len(writeback_args) == 1
        assert 1 in writeback_args[0]


# ---------------------------------------------------------------------------
# DEFECT D — match_subnet_for_ip must not raise on malformed subnet records
# ---------------------------------------------------------------------------

class TestMatchSubnetMalformedRecord:
    """DEFECT D: a bad subnet_address/mask should be skipped; matching continues."""

    def test_bad_subnet_skipped_good_subnet_returned(self):
        subnets = [
            {"subnet_address": "not-an-ip", "subnet_mask": "24"},
            {"_id": 2, "subnet_address": "10.0.1.0", "subnet_mask": "24"},
        ]
        from apps.cmdb.services.ipam_reconcile import match_subnet_for_ip
        result = match_subnet_for_ip("10.0.1.5", subnets)
        assert result is not None
        assert result["_id"] == 2


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
