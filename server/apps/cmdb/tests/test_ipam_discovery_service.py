"""IPAM 发现采集：VM 指标行回写 + 台账写回。"""
import pytest
from types import SimpleNamespace

pytestmark = pytest.mark.unit


class TestApplyIpDiscoveryVmRows:
    def test_按任务所选子网回写_空子网也会触发离线(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        task = SimpleNamespace(params={"subnet_ids": [1, 2]}, instances={})
        calls = []

        def fake_apply(subnet_id, alive):
            calls.append((str(subnet_id), alive))
            return {"created": len(alive), "updated": 0, "offline": 1 if not alive else 0}

        monkeypatch.setattr(ipam_discovery, "apply_discovery_result", fake_apply)

        result = ipam_discovery.apply_ip_discovery_vm_rows(
            task,
            [
                {
                    "collect_status": "success",
                    "subnet_id": "1",
                    "ip_addr": "10.0.1.10",
                    "mac": "AA:BB:CC:DD:EE:FF",
                }
            ],
        )

        assert calls == [
            ("1", [{"ip": "10.0.1.10", "mac": "AA:BB:CC:DD:EE:FF"}]),
            ("2", []),
        ]
        assert result == {"created": 1, "updated": 0, "offline": 1}

    def test_忽略失败行和缺少关键字段的行(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        task = SimpleNamespace(params={}, instances={})
        calls = []
        monkeypatch.setattr(
            ipam_discovery,
            "apply_discovery_result",
            lambda subnet_id, alive: calls.append((subnet_id, alive)) or {"created": 0, "updated": 0, "offline": 0},
        )

        result = ipam_discovery.apply_ip_discovery_vm_rows(
            task,
            [
                {"collect_status": "failed", "subnet_id": "1", "ip_addr": "10.0.1.10"},
                {"collect_status": "success", "subnet_id": "", "ip_addr": "10.0.1.11"},
                {"collect_status": "success", "subnet_id": "1", "ip_addr": ""},
            ],
        )

        assert calls == []
        assert result == {"created": 0, "updated": 0, "offline": 0}


class TestApplyDiscoveryResult:
    def test_在线入账_未探到的自动发现置离线_手工不动(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 11, "ip_addr": "10.0.1.10", "auto_collect": True, "subnet_id": "1"},
            {"_id": 12, "ip_addr": "10.0.1.20", "auto_collect": True, "subnet_id": "1"},
            {"_id": 13, "ip_addr": "10.0.1.30", "auto_collect": False, "subnet_id": "1"},
        ])
        # P0-1.2 修复后,子网有 organization 时才能走 upsert 路径(空 org 会早返回 skipped=True)
        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": [7]}])
        ups, offs = [], []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups.append(kw))
        monkeypatch.setattr(ipam_discovery, "_mark_offline", lambda ip_id: offs.append(ip_id))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1,
            alive=[{"ip": "10.0.1.10", "mac": "AA:BB:CC:DD:EE:FF"}, {"ip": "10.0.1.40", "mac": ""}],
        )
        assert {u["ip_addr"] for u in ups} == {"10.0.1.10", "10.0.1.40"}
        assert offs == [12]
        assert result["offline"] == 1
        assert 13 not in offs

    def test_auto_collect缺失的已有记录不被覆盖(self, monkeypatch):
        """非自动创建的记录（auto_collect 缺失/None）在探到同地址时也不能被覆盖。
        仅 auto_collect is True 的记录才归发现采集所有、可写。"""
        from apps.cmdb.services import ipam_discovery
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 21, "ip_addr": "10.0.1.50", "subnet_id": "1"},  # 无 auto_collect 字段
        ])
        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": []}])
        ups, offs = [], []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups.append(kw))
        monkeypatch.setattr(ipam_discovery, "_mark_offline", lambda ip_id: offs.append(ip_id))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1, alive=[{"ip": "10.0.1.50", "mac": ""}],
        )
        assert ups == []          # 探到同地址但记录非自动创建 -> 不覆盖
        assert offs == []         # 也不会被置离线（offline 仅作用于 auto_collect is True）
        assert result["created"] == 0 and result["updated"] == 0


# ---------------------------------------------------------------------------
# DEFECT A — apply_discovery_result must forward organization from subnet
# ---------------------------------------------------------------------------

class TestApplyDiscoveryResultOrganization:
    """DEFECT A: organization from subnet must be passed through to _upsert_alive_ip."""

    def test_organization_forwarded_to_upsert(self, monkeypatch):
        """apply_discovery_result should load the subnet, extract organization, and
        pass it to every _upsert_alive_ip call (so instance_create never gets []
        when the subnet defines a real org)."""
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(
            ipam_discovery, "_load_subnets_by_ids",
            lambda ids: [{"_id": 1, "organization": [7], "subnet_address": "10.0.1.0", "subnet_mask": "24"}],
        )
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [])
        captured = []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: captured.append(kw))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        ipam_discovery.apply_discovery_result(1, [{"ip": "10.0.1.10", "mac": ""}])

        assert len(captured) == 1
        assert captured[0]["organization"] == [7]


# ---------------------------------------------------------------------------
# DEFECT B — _upsert_alive_ip must write collect_time
# ---------------------------------------------------------------------------

class TestUpsertAliveIpCollectTime:
    """DEFECT B: _upsert_alive_ip payload must include collect_time."""

    def test_collect_time_in_payload(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery
        from apps.cmdb.services.instance import InstanceManage

        captured_payloads = []

        def fake_instance_create(model_id, payload, operator, **kw):
            captured_payloads.append(payload)
            return {"_id": 999}

        monkeypatch.setattr(InstanceManage, "instance_create", staticmethod(fake_instance_create))

        ipam_discovery._upsert_alive_ip(
            existing_id=None,
            subnet_id=1,
            ip_addr="10.0.1.5",
            mac="",
            organization=[1],
        )

        assert len(captured_payloads) == 1
        assert "collect_time" in captured_payloads[0]
        assert captured_payloads[0]["collect_time"]  # non-empty


# ---------------------------------------------------------------------------
# P0-1.2 — apply_discovery_result must guard against missing/empty-org subnet
# ---------------------------------------------------------------------------

class TestApplyDiscoveryResultSubnetMissing:
    """P0-1.2: 子网被删/子网无 org 时,instance_create 会因 is_required 校验崩溃;
    apply_discovery_result 必须早返回(不调 _upsert_alive_ip,避免污染 alive 集合),
    并在 summary 里加 skipped=True 以便上层对账任务感知。"""

    def test_subnet_missing_skips_upsert_and_returns_skipped(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        # 子网不存在
        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [])
        ups_calls = []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups_calls.append(kw))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=999,
            alive=[{"ip": "10.0.1.10", "mac": "AA:BB:CC:DD:EE:FF"}],
        )

        assert ups_calls == [], "子网不存在时不应调 _upsert_alive_ip(否则 instance_create 会因 org=[] 抛 is_required)"
        assert result == {"created": 0, "updated": 0, "offline": 0, "skipped": True}

    def test_subnet_with_empty_org_skips_upsert(self, monkeypatch):
        """子网存在但 organization=[] 时,ip 模型 is_required 也会崩,同样要早返回。"""
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(
            ipam_discovery, "_load_subnets_by_ids",
            lambda ids: [{"_id": 1, "organization": []}],
        )
        ups_calls = []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups_calls.append(kw))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1,
            alive=[{"ip": "10.0.1.10", "mac": ""}],
        )

        assert ups_calls == []
        assert result.get("skipped") is True


# ---------------------------------------------------------------------------
# P0-1.3 — _load_subnets_by_ids must tolerate non-numeric subnet_id
# ---------------------------------------------------------------------------

class TestLoadSubnetsByIdsRobustness:
    """P0-1.3: apply_ip_discovery_vm_rows 的 subnet_id 来源是 VM 指标,外部 collector
    可能传非数字(字段漂移/格式变更)。_load_subnets_by_ids 内的 int() 裸转换
    会让单条脏数据导致整批周期扫描挂掉。"""

    def test_load_subnets_by_ids_skips_non_numeric_values(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        captured_filters: list = []

        def fake_query_entity(*args, **kwargs):
            # 调用形态: ag.query_entity(INSTANCE, [filter_dicts...])
            captured_filters.append(args[1] if len(args) > 1 else kwargs.get("filters"))
            return ([{"_id": 1, "organization": [7], "subnet_address": "10.0.1.0", "subnet_mask": "24"}], 1)

        # 不依赖真实 GraphClient,mock 掉 context manager 入口
        class _FakeAg:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            query_entity = staticmethod(fake_query_entity)

        monkeypatch.setattr(ipam_discovery, "GraphClient", lambda *a, **k: _FakeAg())

        # 混入字符串 "abc"、None、空串,期望被过滤而不是崩
        rows = ipam_discovery._load_subnets_by_ids([1, "abc", None, "", 2])

        assert len(rows) == 1
        assert captured_filters, "query_entity 应被调用"
        id_filter = next(
            (f for f in captured_filters[0] if isinstance(f, dict) and f.get("field") == "id"),
            None,
        )
        assert id_filter is not None, "必须以 id[] 过滤做图查询"
        ids_value = id_filter["value"]
        assert all(isinstance(i, int) and not isinstance(i, bool) for i in ids_value)
        assert set(ids_value) == {1, 2}

    def test_load_subnets_by_ids_returns_empty_when_all_invalid(self, monkeypatch):
        """全是非数字时返回空列表,不抛 ValueError。"""
        from apps.cmdb.services import ipam_discovery

        rows = ipam_discovery._load_subnets_by_ids(["abc", None, ""])
        assert rows == []
