"""IPAM 发现采集:VM 指标行回写 + 台账写回。"""
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def empty_format_data():
    return {"add": [], "update": [], "delete": [], "association": [], "all": 0}


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
                "failed": 0,
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
        assert result["failed"] == 0
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
                "failed": 0,
                "format_data": empty_format_data(),
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
        assert result["failed"] == 0
        assert result["format_data"]["all"] == 0


class TestApplyDiscoveryResult:
    def test_在线入账_未探到的自动发现置离线_手工不动(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 11, "ip_addr": "10.0.1.10", "auto_collect": True, "subnet_id": "1"},
            {"_id": 12, "ip_addr": "10.0.1.20", "auto_collect": True, "subnet_id": "1"},
            {"_id": 13, "ip_addr": "10.0.1.30", "auto_collect": False, "subnet_id": "1"},
        ])
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
        assert len(result["format_data"]["add"]) == 1
        assert len(result["format_data"]["update"]) == 2
        assert 13 not in offs

    def test_auto_collect缺失的已有记录不被覆盖(self, monkeypatch):
        """非自动创建的记录(auto_collect 缺失/None)在探到同地址时也不能被覆盖。"""
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 21, "ip_addr": "10.0.1.50", "subnet_id": "1"},
        ])
        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": [7]}])
        ups, offs = [], []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups.append(kw))
        monkeypatch.setattr(ipam_discovery, "_mark_offline", lambda ip_id: offs.append(ip_id))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1, alive=[{"ip": "10.0.1.50", "mac": ""}],
        )

        assert ups == []
        assert offs == []
        assert result["created"] == 0 and result["updated"] == 0
        assert result["format_data"]["all"] == 0


class TestApplyDiscoveryResultOrganization:
    """DEFECT A: organization from subnet must be passed through to _upsert_alive_ip."""

    def test_organization_forwarded_to_upsert(self, monkeypatch):
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
        assert captured_calls[0]["payload"]["collect_time"]
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


class TestApplyDiscoveryResultSubnetMissing:
    """子网被删/子网无 org 时,必须早返回,避免 instance_create 因 organization 为空崩溃。"""

    def test_subnet_missing_skips_upsert_and_returns_skipped(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [])
        ups_calls = []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups_calls.append(kw))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=999,
            alive=[{"ip": "10.0.1.10", "mac": "AA:BB:CC:DD:EE:FF"}],
        )

        assert ups_calls == []
        assert result["skipped"] is True
        assert result["failed"] == 0
        assert result["format_data"]["all"] == 0

    def test_subnet_with_empty_org_skips_upsert(self, monkeypatch):
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


class TestLoadSubnetsByIdsRobustness:
    """VM 指标的 subnet_id 可能非数字,单条脏数据不能击穿整批。"""

    def test_load_subnets_by_ids_skips_non_numeric_values(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        captured_filters: list = []

        def fake_query_entity(*args, **kwargs):
            captured_filters.append(args[1] if len(args) > 1 else kwargs.get("filters"))
            return ([{"_id": 1, "organization": [7], "subnet_address": "10.0.1.0", "subnet_mask": "24"}], 1)

        class _FakeAg:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            query_entity = staticmethod(fake_query_entity)

        monkeypatch.setattr(ipam_discovery, "GraphClient", lambda *a, **k: _FakeAg())

        rows = ipam_discovery._load_subnets_by_ids([1, "abc", None, "", 2])

        assert len(rows) == 1
        assert captured_filters
        id_filter = next(
            (f for f in captured_filters[0] if isinstance(f, dict) and f.get("field") == "id"),
            None,
        )
        assert id_filter is not None
        ids_value = id_filter["value"]
        assert all(isinstance(i, int) and not isinstance(i, bool) for i in ids_value)
        assert set(ids_value) == {1, 2}

    def test_load_subnets_by_ids_returns_empty_when_all_invalid(self):
        from apps.cmdb.services import ipam_discovery

        rows = ipam_discovery._load_subnets_by_ids(["abc", None, ""])
        assert rows == []


class TestApplyDiscoveryResultPartialFailure:
    """单条 IP 写入失败不应击穿整批,summary 通过 failed 对外暴露。"""

    def test_upsert_failure_for_one_ip_does_not_abort_batch(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": [7]}])
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [])
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        calls = []

        def fake_upsert(**kw):
            calls.append(kw["ip_addr"])
            if kw["ip_addr"] == "10.0.1.20":
                raise RuntimeError("模拟图驱动瞬时失败")

        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", fake_upsert)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1,
            alive=[
                {"ip": "10.0.1.10", "mac": ""},
                {"ip": "10.0.1.20", "mac": ""},
                {"ip": "10.0.1.30", "mac": ""},
            ],
        )

        assert calls == ["10.0.1.10", "10.0.1.20", "10.0.1.30"]
        assert result["created"] == 2
        assert result["failed"] == 1

    def test_mark_offline_failure_does_not_abort_batch(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": [7]}])
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 11, "ip_addr": "10.0.1.10", "auto_collect": True, "subnet_id": "1"},
            {"_id": 12, "ip_addr": "10.0.1.20", "auto_collect": True, "subnet_id": "1"},
        ])
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: None)
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        offs_calls = []

        def fake_mark_offline(ip_id):
            offs_calls.append(ip_id)
            if ip_id == 12:
                raise RuntimeError("模拟离线写入失败")

        monkeypatch.setattr(ipam_discovery, "_mark_offline", fake_mark_offline)

        result = ipam_discovery.apply_discovery_result(subnet_id=1, alive=[])

        assert offs_calls == [11, 12]
        assert result["offline"] == 1
        assert result["failed"] == 1

    def test_partial_failure_summary_includes_failed(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        monkeypatch.setattr(ipam_discovery, "_load_subnets_by_ids", lambda ids: [{"_id": 1, "organization": [7]}])
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [])
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        def fake_upsert(**kw):
            raise RuntimeError("全失败")

        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", fake_upsert)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1,
            alive=[{"ip": "10.0.1.10", "mac": ""}],
        )

        assert result["created"] == 0
        assert result["failed"] == 1
        assert "failed" in result


class TestApplyIpDiscoveryVmRowsSubnetScoping:
    """任务未勾选子网时,不应越权处理 VM 指标里出现的子网。"""

    def test_no_selected_subnet_returns_empty_summary_without_calling_apply(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        task = SimpleNamespace(params={}, instances={})
        apply_calls = []
        monkeypatch.setattr(
            ipam_discovery,
            "apply_discovery_result",
            lambda subnet_id, alive: apply_calls.append((subnet_id, alive)) or {
                "created": 0,
                "updated": 0,
                "offline": 0,
                "failed": 0,
                "format_data": empty_format_data(),
            },
        )

        result = ipam_discovery.apply_ip_discovery_vm_rows(
            task,
            [
                {"subnet_id": "1", "ip_addr": "10.0.1.10", "collect_status": "success"},
                {"subnet_id": "2", "ip_addr": "10.0.2.20", "collect_status": "success"},
            ],
        )

        assert apply_calls == []
        assert result["created"] == 0
        assert result["failed"] == 0
        assert result["format_data"]["all"] == 0

    def test_no_selected_subnet_logs_warning(self, monkeypatch, caplog):
        import logging

        from apps.cmdb.services import ipam_discovery

        task = SimpleNamespace(params={}, instances={})
        monkeypatch.setattr(
            ipam_discovery,
            "apply_discovery_result",
            lambda subnet_id, alive: {"created": 0, "updated": 0, "offline": 0, "failed": 0},
        )

        with caplog.at_level(logging.WARNING, logger="cmdb"):
            ipam_discovery.apply_ip_discovery_vm_rows(task, [])

        assert any("未勾选子网" in r.message for r in caplog.records)

    def test_selected_subnet_scopes_processing_to_task_choice(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        task = SimpleNamespace(params={"subnet_ids": [1, 3]}, instances={})
        apply_calls = []
        monkeypatch.setattr(
            ipam_discovery,
            "apply_discovery_result",
            lambda subnet_id, alive: apply_calls.append((str(subnet_id), [a["ip"] for a in alive]))
            or {"created": len(alive), "updated": 0, "offline": 0, "failed": 0, "format_data": empty_format_data()},
        )

        ipam_discovery.apply_ip_discovery_vm_rows(
            task,
            [
                {"subnet_id": "1", "ip_addr": "10.0.1.10", "collect_status": "success"},
                {"subnet_id": "2", "ip_addr": "10.0.2.20", "collect_status": "success"},
                {"subnet_id": "3", "ip_addr": "10.0.3.30", "collect_status": "success"},
                {"subnet_id": "5", "ip_addr": "10.0.5.50", "collect_status": "success"},
            ],
        )

        processed = {sid for sid, _ in apply_calls}
        assert processed == {"1", "3"}


class TestSystemWriteHelper:
    """系统写 helper 应统一 system 操作员、跳过权限校验、不记变更日志。"""

    def test_system_write_helpers_exist(self):
        from apps.cmdb.services import ipam_discovery

        assert callable(getattr(ipam_discovery, "_system_create_or_update", None))
        assert callable(getattr(ipam_discovery, "_system_update", None))

    def test_upsert_alive_ip_calls_system_create_or_update(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        captured = []

        def fake_system_helper(model_id, instance_info, existing_id=None, organization=None):
            captured.append((model_id, instance_info, existing_id, organization))
            return {"_id": 123, **instance_info}

        monkeypatch.setattr(ipam_discovery, "_system_create_or_update", staticmethod(fake_system_helper))
        monkeypatch.setattr(
            ipam_discovery,
            "_ensure_subnet_ip_association",
            lambda subnet_id, ip_id: {"success": [], "failed": []},
        )

        ipam_discovery._upsert_alive_ip(
            existing_id=None, subnet_id=1, ip_addr="10.0.1.5", mac="AA:BB", organization=[7],
        )

        assert len(captured) == 1
        assert captured[0][0] == "ip"
        assert captured[0][1]["ip_addr"] == "10.0.1.5"
        assert captured[0][2] is None
        assert captured[0][3] == [7]

    def test_mark_offline_calls_system_update(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery

        captured = []

        def fake_system_update(instance_id, instance_info):
            captured.append((instance_id, instance_info))

        monkeypatch.setattr(ipam_discovery, "_system_update", staticmethod(fake_system_update))

        ipam_discovery._mark_offline(99)

        assert len(captured) == 1
        assert captured[0][0] == 99
        assert captured[0][1] == {"ip_status": ["offline"]}


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
