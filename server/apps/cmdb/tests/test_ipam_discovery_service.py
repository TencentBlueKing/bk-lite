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
            return {
                "created": len(alive),
                "updated": 0,
                "offline": 1 if not alive else 0,
                "format_data": {"add": [], "update": [], "delete": [], "association": [], "all": len(alive)},
            }

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
        assert result["created"] == 1
        assert result["offline"] == 1
        assert set(result["format_data"].keys()) == {"add", "update", "delete", "association", "all"}

    def test_忽略失败行和缺少关键字段的行(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        task = SimpleNamespace(params={}, instances={})
        calls = []
        monkeypatch.setattr(
            ipam_discovery,
            "apply_discovery_result",
            lambda subnet_id, alive: calls.append((subnet_id, alive)) or {
                "created": 0,
                "updated": 0,
                "offline": 0,
                "format_data": {"add": [], "update": [], "delete": [], "association": [], "all": 0},
            },
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
        assert result["created"] == 0
        assert result["format_data"]["all"] == 0


class TestApplyDiscoveryResult:
    def test_在线入账_未探到的自动发现置离线_手工不动(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 11, "ip_addr": "10.0.1.10", "auto_collect": True, "subnet_id": "1"},
            {"_id": 12, "ip_addr": "10.0.1.20", "auto_collect": True, "subnet_id": "1"},
            {"_id": 13, "ip_addr": "10.0.1.30", "auto_collect": False, "subnet_id": "1"},
        ])
        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": []}])
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
        assert len(result["format_data"]["add"]) == 1
        assert len(result["format_data"]["update"]) == 2
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
        assert result["format_data"]["all"] == 0


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

        captured_calls = []

        def fake_instance_create(model_id, payload, operator, **kw):
            captured_calls.append({"payload": payload, "kwargs": kw})
            return {"_id": 999}

        monkeypatch.setattr(InstanceManage, "instance_create", staticmethod(fake_instance_create))
        monkeypatch.setattr(
            ipam_discovery,
            "_ensure_subnet_ip_association",
            lambda subnet_id, ip_id: {"success": [], "failed": []},
        )

        ipam_discovery._upsert_alive_ip(
            existing_id=None,
            subnet_id=1,
            ip_addr="10.0.1.5",
            mac="",
            organization=[1],
        )

        assert len(captured_calls) == 1
        assert "collect_time" in captured_calls[0]["payload"]
        assert captured_calls[0]["payload"]["collect_time"]  # non-empty
        assert captured_calls[0]["kwargs"]["allowed_org_ids"] == [1]

    def test_update_branch_passes_allowed_org_ids(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery
        from apps.cmdb.services.instance import InstanceManage

        captured_calls = []

        def fake_instance_update(user_groups, roles, inst_id, payload, operator, **kw):
            captured_calls.append({"inst_id": inst_id, "payload": payload, "kwargs": kw})

        monkeypatch.setattr(InstanceManage, "instance_update", staticmethod(fake_instance_update))
        monkeypatch.setattr(
            ipam_discovery,
            "_ensure_subnet_ip_association",
            lambda subnet_id, ip_id: {"success": [], "failed": []},
        )

        ipam_discovery._upsert_alive_ip(
            existing_id=88,
            subnet_id=1,
            ip_addr="10.0.1.88",
            mac="",
            organization=[7],
        )

        assert len(captured_calls) == 1
        assert captured_calls[0]["inst_id"] == 88
        assert captured_calls[0]["kwargs"]["allowed_org_ids"] == [7]


class TestSubnetAssociation:
    def test_upsert_alive_ip_ensure_subnet_association(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery
        from apps.cmdb.services.instance import InstanceManage

        monkeypatch.setattr(InstanceManage, "instance_create", staticmethod(lambda *a, **k: {"_id": 901}))
        assoc_calls = []
        monkeypatch.setattr(ipam_discovery, "_ensure_subnet_ip_association", lambda subnet_id, ip_id: assoc_calls.append((subnet_id, ip_id)) or {
            "success": [{"model_asst_id": "subnet_group_ip", "src_inst_id": subnet_id, "dst_inst_id": ip_id}],
            "failed": [],
        })

        out = ipam_discovery._upsert_alive_ip(
            existing_id=None,
            subnet_id=7,
            ip_addr="10.0.7.1",
            mac="",
            organization=[1],
        )

        assert assoc_calls == [(7, 901)]
        assert out["assos_result"]["success"][0]["model_asst_id"] == "subnet_group_ip"

    def test_load_subnet_ips_merges_association_and_field_fallback(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(
            ipam_discovery,
            "_load_subnet_associated_ips",
            lambda subnet_id: [
                {"_id": 1, "ip_addr": "10.0.1.10", "subnet_id": "1"},
            ],
        )
        monkeypatch.setattr(
            ipam_discovery,
            "_load_subnet_ips_by_field",
            lambda subnet_id: [
                {"_id": 1, "ip_addr": "10.0.1.10", "subnet_id": "1"},
                {"_id": 2, "ip_addr": "10.0.1.20", "subnet_id": "1"},
            ],
        )

        rows = ipam_discovery._load_subnet_ips(1)

        assert {row["_id"] for row in rows} == {1, 2}
