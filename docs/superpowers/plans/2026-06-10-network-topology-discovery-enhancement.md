# CMDB 网络拓扑发现增强 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `snmp_topo_tool` 的「采集 → 归一化 → 推断 → 收敛」拓扑流水线合入 bk-lite：agent 侧（stargazer）补齐 SNMP 采集能力，server 侧（CMDB collect_plugin）用新流水线替换旧的两阶段关系发现，输出契约（`interface_connect_interface` 关联）不变。

**Architecture:** 数据流为 stargazer agent 采集 SNMP → 每行证据转成 `network_topo_info_gauge` 指标（每个标量字段自动成为标签，per-device 标识是 `instance_id` 标签）→ VictoriaMetrics → server `CollectNetworkMetrics` 按 `instance_id` 聚合证据行 → 新流水线模块（`collect_plugin/topology/`）产出链路 → 映射回 CMDB 接口实例名 → 写 `assos`。agent 与 server **同步升级**，不保留旧 agent 兼容路径。

**Tech Stack:** Python 3.11（snmp_topo_tool，pysnmp 4.4.12）/ Python 3.12 + Django 4.2 + pytest（server，包管理 uv）/ Sanic + pytest（stargazer agent）。

**对应需求文档:** `spec/requirements/CMDB/20260610.CMDB网络拓扑发现增强.md`

**涉及仓库:**
- `/Users/luoyang/Desktop/work/code/weopsx`（根仓库，含 `snmp_topo_tool/`，Phase 0）
- `/Users/luoyang/Desktop/work/code/weopsx/bk-lite`（`rogerly` 分支，Phase 1-3）

**测试设备凭据:** `/Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/.env.lab`（本地文件，**禁止提交**）

---

## 背景知识（执行前必读）

1. **指标编码机制**：agent 的 `plugins/base_utils.py::convert_to_prometheus_format` 把插件结果里每个 item 的非空标量字段变成 Prometheus 标签，metric 名为 `{model_id}_info_gauge`。所以给证据行 dict 加一个 `group` 字段，标签就会自动多一个 `group`，server 端无须改解析。
2. **设备身份**：每台设备的指标行带独立的 `instance_id` 标签（如 `snmp-task-01-10.0.0.1`），server 端 `CollectNetworkMetrics` 用它分组设备；`network_system_info_gauge` 行带 `ip_addr`/`sysname`/`sysobjectid`。
3. **server 端接口实例名**：`interface_index_map[(instance_id, str(ifindex))] -> inst_name`（在 `index_interface_lookup` 中建立）。新流水线的 `port_id` 格式是 `{device_id}:{ifindex}`，device_id 即 instance_id，所以能直接映射。
4. **工具流水线入口**：`parse_aggregate_result(aggregate, previous_links)`，输入 aggregate 结构为 `{"devices": [{"device": {"host": <id>}, "success": True, "collector_result": {"result": {"evidence": {<group>: [rows]}}}}]}`，rows 为 `{"tag":..., "ifindex":..., "val":...}`。
5. **置信度**：工具用 0-100 整数；`CollectModels.topology_contract["min_confidence"]` 是 0-1 浮点，使用时乘 100。
6. **运行 snmp_topo_tool 测试**：`cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool && .venv311/bin/python -m unittest discover -s tests`（必须用 .venv311，pysnmp 4.4.12 不兼容 py3.12+）。
7. **运行 server 测试**：`cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest <path> -v`。
8. **运行 agent 测试**：`cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer && uv run pytest tests/<file> -v`。

---

## Phase 0：snmp_topo_tool 缺陷修复（先修后搬）

### Task 1: CDP/FDP 本地端口解析不再优先查 bridge basePort 映射

CDP/FDP 的 OID 索引第一段就是 ifIndex，现有 `resolve_local_neighbor_port_id` 却先查 bridge basePort→ifIndex 映射，basePort 编号与 ifIndex 重叠时会静默解析到错误端口。

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/parse_topology.py:451-481`（`resolve_local_neighbor_port_id`）及 `parse_topology.py:693` 调用点
- Test: `/Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/tests/test_parse_topology.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_parse_topology.py` 的 `ParseTopologyTest` 类中追加（import 区补 `from parse_topology import resolve_local_neighbor_port_id` 与 `from topology_models import NormalizedPort`，文件顶部 try/except 双导入风格保持一致）：

```python
    def test_cdp_local_index_resolves_as_ifindex_not_bridge_port(self) -> None:
        # bridge basePort "5" -> ifIndex "23"，与 ifIndex "5" 编号重叠。
        # CDP 索引第一段就是 ifIndex，必须解析到 dev:5 而不是 dev:23。
        ports = {
            "dev:5": NormalizedPort(device_id="dev", port_id="dev:5", ifindex="5", ifname="GigabitEthernet0/0/5"),
            "dev:23": NormalizedPort(device_id="dev", port_id="dev:23", ifindex="23", ifname="GigabitEthernet0/0/23"),
        }
        port_id, state = resolve_local_neighbor_port_id(
            device_id="dev",
            local_port_num="5",
            lldp_local_fields={},
            bridge_port_map={"dev": {"5": "23"}},
            ports=ports,
            protocol="cdp",
        )
        self.assertEqual(port_id, "dev:5")
        self.assertEqual(state, "resolved")

    def test_fdp_local_index_resolves_as_ifindex_not_bridge_port(self) -> None:
        ports = {
            "dev:5": NormalizedPort(device_id="dev", port_id="dev:5", ifindex="5", ifname="ethernet1/5"),
            "dev:23": NormalizedPort(device_id="dev", port_id="dev:23", ifindex="23", ifname="ethernet1/23"),
        }
        port_id, state = resolve_local_neighbor_port_id(
            device_id="dev",
            local_port_num="5",
            lldp_local_fields={},
            bridge_port_map={"dev": {"5": "23"}},
            ports=ports,
            protocol="fdp",
        )
        self.assertEqual(port_id, "dev:5")
        self.assertEqual(state, "resolved")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool && .venv311/bin/python -m unittest tests.test_parse_topology.ParseTopologyTest.test_cdp_local_index_resolves_as_ifindex_not_bridge_port -v`
Expected: FAIL（`resolve_local_neighbor_port_id() got an unexpected keyword argument 'protocol'`）

- [ ] **Step 3: 实现**

替换 `parse_topology.py` 中整个 `resolve_local_neighbor_port_id` 函数：

```python
def resolve_local_neighbor_port_id(
    device_id: str,
    local_port_num: str,
    lldp_local_fields: dict[str, str],
    bridge_port_map: dict[str, dict[str, str]],
    ports: dict[str, NormalizedPort],
    protocol: str = "lldp",
) -> tuple[str, str]:
    direct_port_id = f"{device_id}:{local_port_num}"

    local_port_raw = lldp_local_fields.get("LLDP-LocPortId", "")
    local_port_subtype = lldp_local_fields.get("LLDP-LocPortIdSubtype", "")
    local_port_desc = lldp_local_fields.get("LLDP-LocPortDesc", "")
    decoded_local_port, _ = decode_lldp_port_id(local_port_subtype, local_port_raw)
    has_local_name_evidence = bool(decoded_local_port or local_port_desc)

    def matches_local_fields(port: NormalizedPort) -> bool:
        if decoded_local_port and decoded_local_port in {port.ifname, port.ifalias, port.ifdescr, port.ifindex, port.mac}:
            return True
        if local_port_desc and local_port_desc in {port.ifname, port.ifalias, port.ifdescr}:
            return True
        return False

    def find_by_local_fields() -> str | None:
        if not has_local_name_evidence:
            return None
        for port in ports.values():
            if port.device_id == device_id and matches_local_fields(port):
                return port.port_id
        return None

    # CDP/FDP 的索引第一段就是 ifIndex，不存在 basePort 语义，禁止查 bridge 映射。
    if protocol in {"cdp", "fdp"}:
        if direct_port_id in ports:
            return direct_port_id, "resolved"
        matched = find_by_local_fields()
        if matched:
            return matched, "resolved"
        return direct_port_id, "unresolved_local_port"

    bridge_mapped_ifindex = bridge_port_map.get(device_id, {}).get(local_port_num)
    bridge_port_id = f"{device_id}:{bridge_mapped_ifindex}" if bridge_mapped_ifindex else ""

    # bridge 命中后用 LLDP 本地端口名交叉校验；无名称证据时维持原有 bridge 优先行为。
    if bridge_port_id and bridge_port_id in ports:
        if not has_local_name_evidence or matches_local_fields(ports[bridge_port_id]):
            return bridge_port_id, "resolved"

    if direct_port_id in ports:
        if not has_local_name_evidence or matches_local_fields(ports[direct_port_id]):
            return direct_port_id, "resolved"

    matched = find_by_local_fields()
    if matched:
        return matched, "resolved"

    # 名称证据与所有候选都不一致：退回原优先级，避免把可解析端口判为 unresolved。
    if bridge_port_id and bridge_port_id in ports:
        return bridge_port_id, "resolved"
    if direct_port_id in ports:
        return direct_port_id, "resolved"

    return direct_port_id, "unresolved_local_port"
```

更新调用点（`parse_topology.py` 约 693 行，`normalize_topology_data` 内）：

```python
                candidate_port_id, resolution_state = resolve_local_neighbor_port_id(
                    device_id=device_id,
                    local_port_num=local_port_num,
                    lldp_local_fields=local_fields,
                    bridge_port_map=bridge_port_map,
                    ports=ports,
                    protocol=protocol,
                )
```

- [ ] **Step 4: 运行全量测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool && .venv311/bin/python -m unittest discover -s tests -v`
Expected: 全部 PASS（含原有 LLDP basePort 解析测试——无名称证据或名称一致时行为不变）。若 `test_written_parsed_fixture_matches_current_parser_output` 失败，说明 sample 输出受影响：检查差异是否符合本任务语义；符合则用 `.venv311/bin/python -c "import json,parse_topology;from pathlib import Path;Path('parsed_result.sample.json').write_text(json.dumps(parse_topology.parse_result_file(Path('result.sample.json')),ensure_ascii=False,indent=2)+'\n')"` 重新生成 fixture。

- [ ] **Step 5: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx
git add snmp_topo_tool/parse_topology.py snmp_topo_tool/tests/test_parse_topology.py snmp_topo_tool/parsed_result.sample.json
git commit -m "fix(snmp_topo_tool): CDP/FDP 本地索引按 ifIndex 解析，LLDP bridge 命中增加名称交叉校验"
```

### Task 2: fallback 全部跳过时的报错信息修正 + 死代码清理 + QBRIDGE 注释

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/snmp_topo.py:563-585`（`_fallback_walk_cmd`）
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/parse_topology.py:537`（删除死变量）、`parse_topology.py:636-638`（QBRIDGE 注释）
- Test: `/Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/tests/test_snmp_topo.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_snmp_topo.py` 中追加（该文件已有对 `SnmpTopoCollector` 打桩的测试，沿用其风格；若文件内已有构造 collector 的 helper 则复用）：

```python
    def test_fallback_with_no_records_reports_mib_unavailable(self):
        import snmp_topo
        from unittest import mock

        collector = snmp_topo.SnmpTopoCollector.__new__(snmp_topo.SnmpTopoCollector)
        collector.params = snmp_topo.SnmpParams(host="192.0.2.1", community="public")
        collector.oids = list(snmp_topo.DEFAULT_OID_MAP.keys())

        empty = snmp_topo.FallbackOidResult(records=[], skipped=False)
        with mock.patch.object(collector, "_fallback_collect_oid", return_value=empty):
            with self.assertRaises(RuntimeError) as ctx:
                collector._fallback_walk_cmd()
        message = str(ctx.exception)
        self.assertIn("no data", message)
        self.assertNotIn("OID not increasing", message)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool && .venv311/bin/python -m unittest tests.test_snmp_topo -v 2>&1 | tail -5`
Expected: 新测试 FAIL（报错信息仍是 "OID not increasing"）

- [ ] **Step 3: 实现三处修改**

`snmp_topo.py` `_fallback_walk_cmd` 末尾两行替换为：

```python
        if records:
            return records
        raise RuntimeError(
            "SNMP fallback collection returned no data: "
            "device did not respond with any requested MIB subtree"
        )
```

`parse_topology.py` `normalize_topology_data` 中删除这一行（约 537 行，变量从未被使用）：

```python
    unresolved_neighbors: list[dict[str, Any]] = []
```

`parse_topology.py` QBRIDGE VLAN 提取处（`fdb_rows[suffix]["vlan"] = suffix_parts[0]` 上方）加注释：

```python
                    if tag == "QBRIDGE-FdbPort":
                        if len(suffix_parts) > 6:
                            # dot1qTpFdbTable 索引首段是 dot1qFdbId，多数设备等于 VLAN ID，
                            # 但协议不保证；仅用于 VLAN 标注与 per-VLAN 去重粒度，可接受。
                            fdb_rows[suffix]["vlan"] = suffix_parts[0]
```

- [ ] **Step 4: 运行全量测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool && .venv311/bin/python -m unittest discover -s tests`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx
git add snmp_topo_tool/snmp_topo.py snmp_topo_tool/parse_topology.py snmp_topo_tool/tests/test_snmp_topo.py
git commit -m "fix(snmp_topo_tool): fallback 无数据时报错指明 MIB 不可用；清理死代码；QBRIDGE 假设加注释"
```

---

## Phase 1：stargazer agent 采集增强

### Task 3: protocol_oids.py 补齐 OID 注册表并统一 tag 命名

把 OID 覆盖补齐到与 snmp_topo_tool 一致，tag 命名**以工具为准**（server 新流水线按 tag 精确匹配）。同时给每条 OID 加 `group` 字段（证据分组）。涉及 tag 改名：`LLDP-LocalPortId→LLDP-LocPortId`、`CDP-CacheDeviceId→CDP-DeviceId`、`CDP-CacheDevicePort→CDP-DevicePort`、`BRIDGE-MIB-BasePortIfIndex→BRIDGE-BasePortIfIndex`。

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer/plugins/inputs/network_topo/protocol_oids.py`
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer/plugins/inputs/network_topo/snmp_topo.py`（facts 构建器引用的旧 tag 同步改名）
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer/tests/test_network_topo_oids.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_network_topo_oids.py`：

```python
from plugins.inputs.network_topo.protocol_oids import (
    ALL_PROTOCOL_OID_MAP,
    PROTOCOL_OID_GROUPS,
    flatten_oid_registry,
)


REQUIRED_TAGS = {
    # system
    "1.3.6.1.2.1.1.5": ("System-SysName", "system"),
    # interfaces（新增 IFXTable-IfName）
    "1.3.6.1.2.1.31.1.1.1.1": ("IFXTable-IfName", "interfaces"),
    "1.3.6.1.2.1.2.2.1.2": ("IFTable-IfDescr", "interfaces"),
    # lldp 本地端口表与远端补充
    "1.0.8802.1.1.2.1.3.7.1.2": ("LLDP-LocPortIdSubtype", "neighbors"),
    "1.0.8802.1.1.2.1.3.7.1.3": ("LLDP-LocPortId", "neighbors"),
    "1.0.8802.1.1.2.1.3.7.1.4": ("LLDP-LocPortDesc", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.4": ("LLDP-RemChassisIdSubtype", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.5": ("LLDP-RemChassisId", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.6": ("LLDP-RemPortIdSubtype", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.8": ("LLDP-RemPortDesc", "neighbors"),
    # cdp 补充
    "1.3.6.1.4.1.9.9.23.1.2.1.1.3": ("CDP-AddressType", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.4": ("CDP-Address", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.6": ("CDP-DeviceId", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.7": ("CDP-DevicePort", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.8": ("CDP-Platform", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.19": ("CDP-SysName", "neighbors"),
    # fdp
    "1.3.6.1.4.1.1991.1.1.3.1.1.2": ("FDP-DeviceId", "neighbors"),
    "1.3.6.1.4.1.1991.1.1.3.1.1.3": ("FDP-DevicePort", "neighbors"),
    "1.3.6.1.4.1.1991.1.1.3.1.1.4": ("FDP-Platform", "neighbors"),
    "1.3.6.1.4.1.1991.1.1.3.1.1.5": ("FDP-Version", "neighbors"),
    # bridge / fdb / qbridge
    "1.3.6.1.2.1.17.1.4.1.2": ("BRIDGE-BasePortIfIndex", "bridge"),
    "1.3.6.1.2.1.17.4.3.1.2": ("FDB-Port", "fdb"),
    "1.3.6.1.2.1.17.4.3.1.3": ("FDB-Status", "fdb"),
    "1.3.6.1.2.1.17.7.1.2.2.1.2": ("QBRIDGE-FdbPort", "fdb"),
    "1.3.6.1.2.1.17.7.1.2.2.1.3": ("QBRIDGE-FdbStatus", "fdb"),
}


def test_registry_covers_required_oids_with_groups():
    for oid, (tag, group) in REQUIRED_TAGS.items():
        meta = ALL_PROTOCOL_OID_MAP.get(oid)
        assert meta is not None, f"missing OID {oid} ({tag})"
        assert meta["tag"] == tag
        assert meta["group"] == group


def test_every_registry_entry_has_group():
    for entry in flatten_oid_registry():
        assert entry.get("group"), f"OID {entry['key']} missing group"


def test_fdp_is_a_selectable_protocol_group():
    assert "fdp" in PROTOCOL_OID_GROUPS
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer && uv run pytest tests/test_network_topo_oids.py -v`
Expected: FAIL（缺 OID / 缺 group）

- [ ] **Step 3: 实现 protocol_oids.py**

在 `_parse_suffix_index` 之后增加 scalar 解析器：

```python
def _parse_scalar_index(oid, root_oid):
    return ""
```

`PROTOCOL_OID_GROUPS` 全量替换为（每条 OID 增加 `"group"`；保留原 `index_kind`/`default_confidence` 语义；改名按上表）：

```python
PROTOCOL_OID_GROUPS = {
    "system": {
        "oids": [
            {
                "key": "1.3.6.1.2.1.1.5",
                "tag": "System-SysName",
                "ifindex_type": "scalar",
                "index_kind": "scalar",
                "index_parser": _parse_scalar_index,
                "group": "system",
            },
        ],
    },
    "arp": {
        "default_confidence": 0.6,
        "oids": [
            {
                "key": "1.3.6.1.2.1.4.22.1.1",
                "tag": "ARP-IfIndex",
                "ifindex_type": "ipaddr",
                "index_kind": "ipaddr",
                "index_parser": _parse_ipaddr_index,
                "group": "arp",
            },
            {
                "key": "1.3.6.1.2.1.4.22.1.2",
                "tag": "ARP-PhysAddress",
                "ifindex_type": "ipaddr",
                "index_kind": "ipaddr",
                "index_parser": _parse_ipaddr_index,
                "group": "arp",
            },
        ],
    },
    "lldp": {
        "default_confidence": 0.95,
        "oids": [
            {
                "key": "1.0.8802.1.1.2.1.3.7.1.2",
                "tag": "LLDP-LocPortIdSubtype",
                "ifindex_type": "suffix",
                "index_kind": "lldp_local_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.3.7.1.3",
                "tag": "LLDP-LocPortId",
                "ifindex_type": "suffix",
                "index_kind": "lldp_local_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.3.7.1.4",
                "tag": "LLDP-LocPortDesc",
                "ifindex_type": "suffix",
                "index_kind": "lldp_local_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.4",
                "tag": "LLDP-RemChassisIdSubtype",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.5",
                "tag": "LLDP-RemChassisId",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.6",
                "tag": "LLDP-RemPortIdSubtype",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.7",
                "tag": "LLDP-RemPortId",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.8",
                "tag": "LLDP-RemPortDesc",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_port",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.9",
                "tag": "LLDP-RemSysName",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_system",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
        ],
    },
    "cdp": {
        "default_confidence": 0.9,
        "oids": [
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.3",
                "tag": "CDP-AddressType",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.4",
                "tag": "CDP-Address",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
                "tag": "CDP-DeviceId",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
                "tag": "CDP-DevicePort",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.8",
                "tag": "CDP-Platform",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.19",
                "tag": "CDP-SysName",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
        ],
    },
    "fdp": {
        "default_confidence": 0.9,
        "oids": [
            {
                "key": "1.3.6.1.4.1.1991.1.1.3.1.1.2",
                "tag": "FDP-DeviceId",
                "ifindex_type": "suffix",
                "index_kind": "fdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.1991.1.1.3.1.1.3",
                "tag": "FDP-DevicePort",
                "ifindex_type": "suffix",
                "index_kind": "fdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.1991.1.1.3.1.1.4",
                "tag": "FDP-Platform",
                "ifindex_type": "suffix",
                "index_kind": "fdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
            {
                "key": "1.3.6.1.4.1.1991.1.1.3.1.1.5",
                "tag": "FDP-Version",
                "ifindex_type": "suffix",
                "index_kind": "fdp_cache",
                "index_parser": _parse_suffix_index,
                "group": "neighbors",
            },
        ],
    },
    "fdb": {
        "default_confidence": 0.7,
        "oids": [
            {
                "key": "1.3.6.1.2.1.17.1.4.1.2",
                "tag": "BRIDGE-BasePortIfIndex",
                "ifindex_type": "default",
                "index_kind": "bridge_port",
                "index_parser": _parse_default_index,
                "group": "bridge",
            },
            {
                "key": "1.3.6.1.2.1.17.4.3.1.1",
                "tag": "FDB-MacAddress",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
                "group": "fdb",
            },
            {
                "key": "1.3.6.1.2.1.17.4.3.1.2",
                "tag": "FDB-Port",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
                "group": "fdb",
            },
            {
                "key": "1.3.6.1.2.1.17.4.3.1.3",
                "tag": "FDB-Status",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
                "group": "fdb",
            },
            {
                "key": "1.3.6.1.2.1.17.7.1.2.2.1.2",
                "tag": "QBRIDGE-FdbPort",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
                "group": "fdb",
            },
            {
                "key": "1.3.6.1.2.1.17.7.1.2.2.1.3",
                "tag": "QBRIDGE-FdbStatus",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
                "group": "fdb",
            },
        ],
    },
    "interface": {
        "oids": [
            {
                "key": "1.3.6.1.2.1.2.2.1.2",
                "tag": "IFTable-IfDescr",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
                "group": "interfaces",
            },
            {
                "key": "1.3.6.1.2.1.2.2.1.6",
                "tag": "IFTable-PhysAddress",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
                "group": "interfaces",
            },
            {
                "key": "1.3.6.1.2.1.31.1.1.1.1",
                "tag": "IFXTable-IfName",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
                "group": "interfaces",
            },
            {
                "key": "1.3.6.1.2.1.31.1.1.1.18",
                "tag": "IFTable-IfAlias",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
                "group": "interfaces",
            },
        ],
    },
    "ipaddr": {
        "oids": [
            {
                "key": "1.3.6.1.2.1.4.20.1.1",
                "tag": "IpAddr-IpAddr",
                "ifindex_type": "ipaddr",
                "index_kind": "ipaddr",
                "index_parser": _parse_ipaddr_index,
                "group": "ip",
            },
        ],
    },
}
```

文件末尾 `NETWORK_TOPO_REGISTRY` 行更新（基础组加 system）：

```python
NETWORK_TOPO_REGISTRY = flatten_oid_registry(("system", "arp", "interface", "ipaddr"))
```

- [ ] **Step 4: 同步更新 snmp_topo.py 的旧 tag 引用**

`plugins/inputs/network_topo/snmp_topo.py` 中按改名替换（共 4 处字符串）：
- `_build_lldp_topology_facts`：`"LLDP-LocalPortId"` → `"LLDP-LocPortId"`
- `_build_cdp_topology_facts`：`"CDP-CacheDevicePort"` → `"CDP-DevicePort"`、`"CDP-CacheDeviceId"` → `"CDP-DeviceId"`
- `_build_fdb_topology_facts`：`"BRIDGE-MIB-BasePortIfIndex"` → `"BRIDGE-BasePortIfIndex"`

并把 `SnmpTopo.BASE_COLLECTION_PROTOCOLS` 改为：

```python
    BASE_COLLECTION_PROTOCOLS = ("system", "arp", "interface", "ipaddr")
    DEFAULT_TOPOLOGY_PROTOCOLS = ("lldp", "cdp", "fdp", "fdb", "arp")
    SUPPORTED_TOPOLOGY_FACT_PROTOCOLS = ("lldp", "cdp", "fdb", "arp")
```

- [ ] **Step 5: 运行测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer && uv run pytest tests/test_network_topo_oids.py -v && uv run pytest tests/ -v 2>&1 | tail -15`
Expected: 新测试 PASS；存量测试无回归（若存量测试断言了旧 tag 名，按改名同步修正断言）。

- [ ] **Step 6: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add agents/stargazer/plugins/inputs/network_topo/protocol_oids.py agents/stargazer/plugins/inputs/network_topo/snmp_topo.py agents/stargazer/tests/test_network_topo_oids.py
git commit -m "feat(stargazer): network_topo 补齐 LLDP/CDP/FDP/QBRIDGE/FDB-Status/sysName 采集并加证据分组"
```

### Task 4: snmp_topo.py 移植 bulkCmd 降级采集 + 证据行携带 group

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer/plugins/inputs/network_topo/snmp_topo.py`
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer/tests/test_snmp_topo_fallback.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_snmp_topo_fallback.py`：

```python
from unittest import mock

import pytest

from plugins.inputs.network_topo import snmp_topo as topo_mod
from plugins.inputs.network_topo.snmp_topo import FallbackOidResult, SnmpTopo


def _make_collector():
    collector = SnmpTopo.__new__(SnmpTopo)
    collector.host = "192.0.2.1"
    collector.snmp_port = 161
    collector.oids = SnmpTopo._build_oids(None)
    return collector


def test_build_oid_dict_carries_group():
    record = topo_mod.build_oid_dict("1.3.6.1.2.1.2.2.1.2.7", "GigabitEthernet0/0/7")
    assert record["group"] == "interfaces"
    record = topo_mod.build_oid_dict("1.3.6.1.2.1.17.1.4.1.2.5", "23")
    assert record["group"] == "bridge"


def test_bulk_cmd_falls_back_per_oid_on_retryable_error():
    collector = _make_collector()
    fallback_records = [{"tag": "IFTable-IfDescr", "ifindex": "1", "val": "eth0", "group": "interfaces"}]
    with mock.patch.object(
        collector, "_bulk_walk_all", side_effect=RuntimeError("OID not increasing")
    ), mock.patch.object(
        collector, "_fallback_walk_cmd", return_value=fallback_records
    ) as fallback:
        result = collector.bulkCmd()
    fallback.assert_called_once()
    assert result == fallback_records


def test_fallback_skips_optional_oid_and_keeps_required():
    collector = _make_collector()

    def fake_collect(oid):
        if oid in topo_mod.OPTIONAL_FALLBACK_ROOTS:
            return FallbackOidResult(records=[], skipped=True)
        return FallbackOidResult(records=[{"tag": "x", "root": oid, "group": "interfaces"}])

    with mock.patch.object(collector, "_fallback_collect_oid", side_effect=fake_collect):
        records = collector._fallback_walk_cmd()
    assert records  # 可选 OID 跳过不影响整体


def test_fallback_raises_when_required_oid_skipped():
    collector = _make_collector()
    required_oid = "1.3.6.1.2.1.2.2.1.2"  # IFTable-IfDescr 属于必采

    def fake_collect(oid):
        if oid == required_oid:
            return FallbackOidResult(records=[], skipped=True)
        return FallbackOidResult(records=[{"tag": "x", "root": oid, "group": "interfaces"}])

    with mock.patch.object(collector, "_fallback_collect_oid", side_effect=fake_collect):
        with pytest.raises(topo_mod.IncompleteFallbackError):
            collector._fallback_walk_cmd()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer && uv run pytest tests/test_snmp_topo_fallback.py -v`
Expected: FAIL（`FallbackOidResult`/`OPTIONAL_FALLBACK_ROOTS`/`_bulk_walk_all` 不存在）

- [ ] **Step 3: 实现**

在 `plugins/inputs/network_topo/snmp_topo.py` 中（参照工具 `snmp_topo_tool/snmp_topo.py:254-611` 的已验证实现移植，适配点：类名 `SnmpTopo`、属性 `self.cmdGen/self.auth/self.transport_opts/self.host/self.snmp_port`、结果格式化复用现有 `_format_result`）：

模块级新增（`OIDKEY` 定义之后）：

```python
GROUP = "group"

OPTIONAL_FALLBACK_ROOTS = {
    "1.3.6.1.2.1.1.5",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.3",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.4",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.8",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.19",
    "1.3.6.1.4.1.1991.1.1.3.1.1.2",
    "1.3.6.1.4.1.1991.1.1.3.1.1.3",
    "1.3.6.1.4.1.1991.1.1.3.1.1.4",
    "1.3.6.1.4.1.1991.1.1.3.1.1.5",
    "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "1.3.6.1.2.1.17.7.1.2.2.1.3",
}


class IncompleteFallbackError(RuntimeError):
    pass


class FallbackOidResult:
    def __init__(self, records, skipped=False):
        self.records = records
        self.skipped = skipped
```

`build_oid_dict` 返回值增加 group（在返回 dict 中加一项）：

```python
    return {
        ROOT: root_oid,
        KEY: oid,
        TAG: oid_dict.get("tag", "") or oid,
        IF_INDEX: ifIndex,
        IF_INDEX_TYPE: ifindex_type,
        VAL: val,
        GROUP: oid_dict.get("group", "interfaces"),
    }
```

`build_single_oid_dict` 同样加 `GROUP: oid_dict.get("group", "interfaces")`。

`SnmpTopo` 类内新增方法（原 `bulkCmd` 主体抽为 `_bulk_walk_all`，`bulkCmd` 变为带降级的入口）：

```python
    @staticmethod
    def _is_retryable_fallback_error(error):
        message = str(error).lower()
        return "oid not increasing" in message or "empty snmp response message" in message

    def _bulk_walk_all(self):
        eval_oids = self.oids
        oids = self._format_oids(self.oids)
        errorIndication, errorStatus, errorIndex, varBindTable = self.cmdGen.bulkCmd(
            self.auth,
            cmdgen.UdpTransportTarget((self.host, self.snmp_port), **self.transport_opts),
            0,
            25,
            *oids,
            lookupMib=False,
        )
        if errorIndication:
            raise RuntimeError(str(errorIndication))
        return self._format_result(varBindTable, eval_oids)

    def bulkCmd(self):
        """批量获取 OID 数据，失败时按 OID 逐个降级采集"""
        try:
            return self._bulk_walk_all()
        except RuntimeError as err:
            if not self._is_retryable_fallback_error(err):
                raise
            logger.warning(
                f"bulkCmd retryable error host={self.host}, falling back to per-OID walk: {err}"
            )
            return self._fallback_walk_cmd()

    def _is_scalar_oid(self, root_oid):
        from plugins.inputs.network_topo.protocol_oids import get_oid_meta
        return get_oid_meta(root_oid).get("ifindex_type") == "scalar"

    def _walk_oid_with_next_cmd(self, oid):
        errorIndication, errorStatus, errorIndex, varBindTable = self.cmdGen.nextCmd(
            self.auth,
            cmdgen.UdpTransportTarget((self.host, self.snmp_port), **self.transport_opts),
            *self._format_oids([oid]),
            lookupMib=False,
            lexicographicMode=False,
            ignoreNonIncreasingOid=True,
        )
        if errorIndication:
            if self._is_retryable_fallback_error(errorIndication):
                logger.warning(f"Skipping OID subtree host={self.host} oid={oid}: {errorIndication}")
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(str(errorIndication))
        if errorStatus:
            if self._is_retryable_fallback_error(errorStatus):
                logger.warning(f"Skipping OID subtree host={self.host} oid={oid}: {errorStatus.prettyPrint()}")
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(f"SNMP error: {errorStatus.prettyPrint()} (oid={oid})")
        return FallbackOidResult(records=self._format_result(varBindTable, [oid]))

    def _get_scalar_oid(self, oid):
        errorIndication, errorStatus, errorIndex, varBinds = self.cmdGen.getCmd(
            self.auth,
            cmdgen.UdpTransportTarget((self.host, self.snmp_port), **self.transport_opts),
            *self._format_oids([f"{oid}.0"]),
            lookupMib=False,
        )
        if errorIndication:
            if self._is_retryable_fallback_error(errorIndication):
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(str(errorIndication))
        if errorStatus:
            if self._is_retryable_fallback_error(errorStatus):
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(f"SNMP error: {errorStatus.prettyPrint()} (oid={oid})")
        return FallbackOidResult(records=self._format_result([varBinds], [oid]))

    def _fallback_collect_oid(self, oid):
        if self._is_scalar_oid(oid):
            return self._get_scalar_oid(oid)
        return self._walk_oid_with_next_cmd(oid)

    def _fallback_walk_cmd(self):
        records = []
        skipped_required_oids = []
        for oid in self.oids:
            oid_result = self._fallback_collect_oid(oid)
            if oid_result.skipped:
                if oid in OPTIONAL_FALLBACK_ROOTS:
                    logger.info(f"Optional fallback OID unavailable host={self.host} oid={oid}; continuing")
                    continue
                skipped_required_oids.append(oid)
                continue
            records.extend(oid_result.records)
        if skipped_required_oids:
            raise IncompleteFallbackError(
                "Fallback walk skipped required OIDs: " + ", ".join(skipped_required_oids)
            )
        if records:
            return records
        raise RuntimeError(
            "SNMP fallback collection returned no data: "
            "device did not respond with any requested MIB subtree"
        )
```

- [ ] **Step 4: 运行测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer && uv run pytest tests/test_snmp_topo_fallback.py tests/test_network_topo_oids.py -v && uv run pytest tests/ 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add agents/stargazer/plugins/inputs/network_topo/snmp_topo.py agents/stargazer/tests/test_snmp_topo_fallback.py
git commit -m "feat(stargazer): network_topo bulkCmd 失败按 OID 降级采集，证据行携带 group 标签"
```

---

## Phase 2：server CMDB 拓扑流水线

### Task 5: 移植流水线模块 topology/（models + parse）

**Files:**
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/topology/__init__.py`
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/topology/models.py`
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/topology/parse.py`

- [ ] **Step 1: 复制 models.py**

```bash
cp /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/topology_models.py \
   /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/topology/models.py
```

内容不需要修改（纯 dataclass，无外部依赖）。

- [ ] **Step 2: 复制并适配 parse.py**

```bash
cp /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/parse_topology.py \
   /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/topology/parse.py
```

对 `parse.py` 做且仅做以下修改（核心算法零改动——Phase 0 的修复已包含在源文件里）：

1. 文件头 import 区替换为：

```python
from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Any

from apps.cmdb.collection.collect_plugin.topology.models import (
    ArpObservation,
    FdbObservation,
    LinkCandidate,
    NeighborObservation,
    NormalizedDevice,
    NormalizedPort,
)
```

2. 删除文件 I/O 相关函数：`load_result_json`、`load_previous_relationships`、`parse_result_file`（server 端入口只用 `parse_aggregate_result`）。
3. 其余内容（含 `parse_aggregate_result`）原样保留。

- [ ] **Step 3: 创建 `__init__.py`**

```python
from apps.cmdb.collection.collect_plugin.topology.parse import parse_aggregate_result  # noqa: F401
```

- [ ] **Step 4: 冒烟验证导入**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run python -c "from apps.cmdb.collection.collect_plugin.topology import parse_aggregate_result; print(parse_aggregate_result({'devices': []})['summary'])"`
Expected: 输出 `{'devices': 0, 'ports': 0, ...}` 无异常

- [ ] **Step 5: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/collection/collect_plugin/topology/
git commit -m "feat(cmdb): 移植 snmp_topo_tool 拓扑归一化/推断/收敛流水线"
```

### Task 6: 迁移流水线回归测试

**Files:**
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/tests/test_topology_parse_pure.py`

- [ ] **Step 1: 复制测试并适配**

```bash
cp /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/tests/test_parse_topology.py \
   /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/tests/test_topology_parse_pure.py
```

对新文件做且仅做以下修改：

1. import 区替换为（去掉 `parse_result_file` 与 tempfile/Path/json 中仅供文件测试使用的部分，按剩余用量保留）：

```python
from apps.cmdb.collection.collect_plugin.topology.models import NormalizedPort
from apps.cmdb.collection.collect_plugin.topology.parse import (
    parse_aggregate_result,
    resolve_local_neighbor_port_id,
)
```

   （若原文件还从 `parse_topology` import 了其他在测函数，按同样路径搬过来。）
2. 删除依赖磁盘 fixture / `parse_result_file` 的测试方法：`test_sample_fixture_produces_single_inferred_relationship`、`test_written_parsed_fixture_matches_current_parser_output`，以及 1890-1970 行附近所有调用 `parse_result_file(...)` 的测试（用 `grep -n "parse_result_file" test_topology_parse_pure.py` 找全后删除整个方法）。
3. 文件顶部加 pytest 分层标记：

```python
import pytest

pytestmark = pytest.mark.unit
```

- [ ] **Step 2: 运行迁移后的测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/test_topology_parse_pure.py -v 2>&1 | tail -10`
Expected: 全部 PASS（这些是 _pure 层测试，不触 DB）

- [ ] **Step 3: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/tests/test_topology_parse_pure.py
git commit -m "test(cmdb): 迁移拓扑流水线回归测试到 server"
```

### Task 7: 指标行 → 流水线输入适配器

**Files:**
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/topology/adapter.py`
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/tests/test_topology_adapter_pure.py`

- [ ] **Step 1: 写失败测试**

创建 `apps/cmdb/tests/test_topology_adapter_pure.py`：

```python
import pytest

from apps.cmdb.collection.collect_plugin.topology.adapter import build_pipeline_aggregate

pytestmark = pytest.mark.unit


def _row(instance_id, tag, ifindex, val, group=None):
    row = {"instance_id": instance_id, "tag": tag, "ifindex": ifindex, "val": val}
    if group:
        row["group"] = group
    return row


def test_groups_rows_by_instance_and_evidence_group():
    rows = [
        _row("dev-a", "IFTable-IfDescr", "1", "Gi0/0/1", group="interfaces"),
        _row("dev-a", "ARP-PhysAddress", "10.0.0.2", "0xaabbccddeeff", group="arp"),
        _row("dev-b", "System-SysName", "", "sw-b", group="system"),
    ]
    aggregate = build_pipeline_aggregate(rows)
    devices = {item["device"]["host"]: item for item in aggregate["devices"]}
    assert set(devices) == {"dev-a", "dev-b"}
    evidence_a = devices["dev-a"]["collector_result"]["result"]["evidence"]
    assert [r["val"] for r in evidence_a["interfaces"]] == ["Gi0/0/1"]
    assert [r["val"] for r in evidence_a["arp"]] == ["0xaabbccddeeff"]
    assert devices["dev-b"]["collector_result"]["result"]["evidence"]["system"][0]["val"] == "sw-b"


def test_falls_back_to_tag_mapping_when_group_label_missing():
    rows = [_row("dev-a", "BRIDGE-BasePortIfIndex", "5", "23")]
    aggregate = build_pipeline_aggregate(rows)
    evidence = aggregate["devices"][0]["collector_result"]["result"]["evidence"]
    assert evidence["bridge"][0]["val"] == "23"


def test_rows_without_instance_or_known_tag_are_dropped():
    rows = [
        _row("", "IFTable-IfDescr", "1", "x"),
        _row("dev-a", "Unknown-Tag", "1", "x"),
    ]
    aggregate = build_pipeline_aggregate(rows)
    assert aggregate["devices"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/test_topology_adapter_pure.py -v`
Expected: FAIL（adapter 模块不存在）

- [ ] **Step 3: 实现 adapter.py**

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any

# 兜底映射：理论上升级后的 agent 都带 group 标签，这里防御标签缺失的行。
TAG_GROUP_MAP = {
    "System-SysName": "system",
    "IFTable-IfDescr": "interfaces",
    "IFTable-PhysAddress": "interfaces",
    "IFXTable-IfName": "interfaces",
    "IFTable-IfAlias": "interfaces",
    "IpAddr-IpAddr": "ip",
    "ARP-IfIndex": "arp",
    "ARP-PhysAddress": "arp",
    "LLDP-LocPortIdSubtype": "neighbors",
    "LLDP-LocPortId": "neighbors",
    "LLDP-LocPortDesc": "neighbors",
    "LLDP-RemChassisIdSubtype": "neighbors",
    "LLDP-RemChassisId": "neighbors",
    "LLDP-RemPortIdSubtype": "neighbors",
    "LLDP-RemPortId": "neighbors",
    "LLDP-RemPortDesc": "neighbors",
    "LLDP-RemSysName": "neighbors",
    "CDP-AddressType": "neighbors",
    "CDP-Address": "neighbors",
    "CDP-DeviceId": "neighbors",
    "CDP-DevicePort": "neighbors",
    "CDP-Platform": "neighbors",
    "CDP-SysName": "neighbors",
    "FDP-DeviceId": "neighbors",
    "FDP-DevicePort": "neighbors",
    "FDP-Platform": "neighbors",
    "FDP-Version": "neighbors",
    "BRIDGE-BasePortIfIndex": "bridge",
    "FDB-MacAddress": "fdb",
    "FDB-Port": "fdb",
    "FDB-Status": "fdb",
    "QBRIDGE-FdbPort": "fdb",
    "QBRIDGE-FdbStatus": "fdb",
}


def build_pipeline_aggregate(topo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """把 network_topo_info_gauge 指标行聚合成拓扑流水线的 aggregate 输入。

    device_id 使用指标行的 instance_id 标签，与
    CollectNetworkMetrics.interface_index_map 的键空间保持一致。
    """
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in topo_rows:
        instance_id = str(row.get("instance_id", "") or "")
        tag = str(row.get("tag", "") or "")
        group = str(row.get("group", "") or "") or TAG_GROUP_MAP.get(tag, "")
        if not instance_id or not group:
            continue
        grouped[instance_id][group].append(
            {
                "tag": tag,
                "ifindex": str(row.get("ifindex", "") or ""),
                "val": str(row.get("val", "") or ""),
            }
        )

    return {
        "devices": [
            {
                "device": {"host": instance_id},
                "success": True,
                "collector_result": {"result": {"evidence": dict(evidence)}},
            }
            for instance_id, evidence in grouped.items()
        ]
    }
```

- [ ] **Step 4: 运行测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/test_topology_adapter_pure.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/collection/collect_plugin/topology/adapter.py server/apps/cmdb/tests/test_topology_adapter_pure.py
git commit -m "feat(cmdb): 拓扑指标行到流水线输入的适配器"
```

### Task 8: CollectModels 增加 topology_snapshot 字段

用于保存本轮链路快照（下一轮 stale 对比的 previous snapshot）和 confidence/stale/unresolved 排查数据。

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/models/collect_model.py`（`CollectModels` 类内）
- Create: migration（自动生成）

- [ ] **Step 1: 加字段**

在 `CollectModels` 的 `format_data = JSONField(...)` 字段附近追加：

```python
    topology_snapshot = models.JSONField(default=dict, blank=True, help_text="网络拓扑链路快照与排查数据（confidence/stale/unresolved）")
```

（该文件若用 `from django.db.models import JSONField` 风格则保持一致写法。）

- [ ] **Step 2: 生成并应用 migration**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run python manage.py makemigrations cmdb && uv run python manage.py migrate cmdb`
Expected: 生成 `apps/cmdb/migrations/00XX_collectmodels_topology_snapshot.py` 并应用成功

- [ ] **Step 3: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/models/collect_model.py server/apps/cmdb/migrations/
git commit -m "feat(cmdb): CollectModels 增加 topology_snapshot 字段"
```

### Task 9: network.py 用新流水线替换两阶段关系发现

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/collection/collect_plugin/network.py`
- Test: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/tests/e2e/test_network_pipeline.py`（下一个 Task 全面更新，本 Task 先保证可运行的最小新测试）

- [ ] **Step 1: 写失败测试**

在 `apps/cmdb/tests/e2e/test_network_pipeline.py` 末尾追加新测试（沿用文件内现有 `_build_metric`/`_build_network_vm_response`/`_run_network_pipeline`/`_find_interface` helper；`_run_network_pipeline` 需先按下述修改支持 `topology_contract`）：

`_run_network_pipeline` 中 `fake_task` 行替换为：

```python
    fake_task = SimpleNamespace(
        id=7001,
        is_network_topo=topo_enabled,
        instances=[],
        topology_contract={
            "has_network_topo": topo_enabled,
            "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
            "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
            "min_confidence": 0.0,
        },
        topology_snapshot={},
    )
```

并在 `monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", ...)` 之后追加一行（避免测试触 DB 持久化）：

```python
    monkeypatch.setattr(CollectNetworkMetrics, "save_topology_snapshot", lambda self, snapshot: None)
```

新测试函数：

```python
def test_pipeline_builds_connection_from_lldp_evidence_rows(monkeypatch):
    dev1 = "snmp-task-01-10.0.0.1"
    dev2 = "snmp-task-01-10.0.0.2"

    def topo(instance_id, tag, ifindex, val, group):
        return _build_metric(
            NETWORK_TOPOLOGY_METRIC, instance_id,
            tag=tag, ifindex=ifindex, val=val, group=group,
        )

    vm_resp = _build_network_vm_response(
        # dev1 证据：接口表 + 系统名 + LLDP 邻居指向 dev2
        topo(dev1, "System-SysName", "", "edge-sw-1", "system"),
        topo(dev1, "IFXTable-IfName", "101", "GigabitEthernet1/0/1", "interfaces"),
        topo(dev1, "IFTable-IfDescr", "101", "GigabitEthernet1/0/1", "interfaces"),
        topo(dev1, "IFTable-PhysAddress", "101", "0x00aabbccdd01", "interfaces"),
        topo(dev1, "LLDP-RemSysName", "0.101.1", "dist-sw-1", "neighbors"),
        topo(dev1, "LLDP-RemPortId", "0.101.1", "GigabitEthernet1/0/24", "neighbors"),
        topo(dev1, "LLDP-RemPortIdSubtype", "0.101.1", "5", "neighbors"),
        topo(dev1, "LLDP-RemChassisId", "0.101.1", "dist-sw-1", "neighbors"),
        # dev2 证据：接口表 + 系统名
        topo(dev2, "System-SysName", "", "dist-sw-1", "system"),
        topo(dev2, "IFXTable-IfName", "202", "GigabitEthernet1/0/24", "interfaces"),
        topo(dev2, "IFTable-IfDescr", "202", "GigabitEthernet1/0/24", "interfaces"),
        topo(dev2, "IFTable-PhysAddress", "202", "0x00aabbccdd02", "interfaces"),
    )
    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    src = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assos = [a for a in src.get("assos", []) if a["model_asst_id"] == "interface_connect_interface"]
    assert assos == [{
        "asst_id": "connect",
        "inst_name": "10.0.0.2-switch-dist-downlink",
        "model_asst_id": "interface_connect_interface",
        "model_id": "interface",
    }]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py::test_pipeline_builds_connection_from_lldp_evidence_rows -v`
Expected: FAIL（`save_topology_snapshot` 不存在 / 旧逻辑产不出该关联）

- [ ] **Step 3: 重构 network.py**

1. 文件头 import 增加两行新导入，并把现有 `from apps.cmdb.models import OidMapping` 一行改为合并导入：

```python
from apps.cmdb.collection.collect_plugin.topology.adapter import build_pipeline_aggregate
from apps.cmdb.collection.collect_plugin.topology.parse import parse_aggregate_result
from apps.cmdb.models import CollectModels, OidMapping
```

2. `set_metrics` 中不再查询 facts 指标，替换为：

```python
    def set_metrics(self):
        if self.is_topo:
            if NETWORK_INTERFACES_RELATIONS not in self._metrics:
                self._metrics.append(NETWORK_INTERFACES_RELATIONS)
            self.collection_metrics_dict.setdefault(NETWORK_INTERFACES_RELATIONS, [])
```

3. `format_metrics` 中两行 pop 保留 `topo_data`，facts pop 行改为丢弃（agent 仍会上报 facts 指标但 server 不消费；该指标已不在查询里，pop 仅为防御）：

```python
        topo_data = self.collection_metrics_dict.pop(NETWORK_INTERFACES_RELATIONS, [])
        self.collection_metrics_dict.pop(NETWORK_TOPOLOGY_FACTS, None)
```

   末尾调用处改为：

```python
        if self.is_topo:
            relationships = self.collect_topology_relationships(topo_data)
            self.add_interface_assos(relationships)
```

4. **替换** `collect_topology_relationships`（旧签名两个参数 → 新签名一个参数），并**删除**以下旧方法：`find_topology_fact_relationships`、`resolve_topology_fact_interface`、`resolve_device_instance_id`、`index_device_lookup`、`find_interface_relationships`、`set_alias_descr`、`normalize_mac`；`__init__` 中删除 `self.device_lookup_map = defaultdict(set)`；`format_metrics` 中删除 `self.index_device_lookup(index_data)` 调用行。新实现：

```python
    def collect_topology_relationships(self, topo_data):
        aggregate = build_pipeline_aggregate(topo_data)
        previous_links = self.get_previous_topology_links()
        parsed = parse_aggregate_result(aggregate, previous_links=previous_links)

        contract = self.collect_inst.topology_contract
        min_confidence = int(float(contract.get("min_confidence", 0) or 0) * 100)

        topology = parsed["topology"]
        current_links = list(topology["authoritative_links"]) + list(topology["inferred_links"])
        relationships, dropped = [], []
        seen = set()
        for link in current_links:
            if link.get("relationship_type") != "authoritative" and int(link.get("confidence", 0) or 0) < min_confidence:
                dropped.append({"reason": "below_min_confidence", **self.slim_link(link)})
                continue
            source_inst_name = self.resolve_pipeline_inst_name(link.get("source_port_id"))
            target_inst_name = self.resolve_pipeline_inst_name(link.get("target_port_id"))
            if not source_inst_name or not target_inst_name or source_inst_name == target_inst_name:
                dropped.append({"reason": "interface_not_in_inventory", **self.slim_link(link)})
                continue
            relation = {
                "source_inst_name": source_inst_name,
                "target_inst_name": target_inst_name,
                "model_id": "interface",
                "asst_id": "connect",
                "model_asst_id": "interface_connect_interface",
            }
            self.append_unique_relationship(relationships, seen, relation)

        self.save_topology_snapshot(
            {
                "links": [self.slim_link(link) for link in current_links],
                "stale_links": [self.slim_link(link) for link in topology["stale_links"]],
                "unresolved_neighbors": topology["unresolved_neighbors"],
                "dropped": dropped,
                "summary": parsed["summary"],
            }
        )
        return relationships

    def resolve_pipeline_inst_name(self, port_id):
        """port_id 形如 '{instance_id}:{ifindex}'，映射回 CMDB 接口实例名。"""
        if not port_id or ":" not in str(port_id):
            return None
        instance_id, ifindex = str(port_id).rsplit(":", 1)
        return self.interface_index_map.get((instance_id, ifindex))

    @staticmethod
    def slim_link(link):
        keys = (
            "relationship_id", "relationship_type", "evidence_source", "confidence",
            "source_device", "source_port_id", "source_inst_name",
            "target_device", "target_port_id", "target_inst_name",
            "remote_device_name", "remote_port_name", "vlan", "status",
        )
        return {key: link.get(key) for key in keys if link.get(key) is not None}

    def get_previous_topology_links(self):
        snapshot = getattr(self.collect_inst, "topology_snapshot", None) or {}
        links = snapshot.get("links", [])
        return links if isinstance(links, list) else []

    def save_topology_snapshot(self, snapshot):
        CollectModels.objects.filter(id=self.task_id).update(topology_snapshot=snapshot)
```

   注意：`__init__` 中已有 `self.collect_inst = self.get_collect_inst()`，`self.task_id` 来自基类。

5. `__init__` 中 `self.device_lookup_map` 删除后，确认文件内无其他引用：`grep -n "device_lookup_map\|find_topology_fact\|resolve_topology_fact\|find_interface_relationships\|set_alias_descr" network.py` 应无结果。

- [ ] **Step 4: 运行新测试与全量 cmdb 测试**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py::test_pipeline_builds_connection_from_lldp_evidence_rows -v`
Expected: PASS
Run: `uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py -v 2>&1 | tail -20`
Expected: 旧的 facts 路径测试（`test_network_topology_prefers_fact_payload_when_resolvable` 等 4 个 topo 测试）FAIL —— 这是预期，下一 Task 处理。

- [ ] **Step 5: Commit（连同下一 Task 的 e2e 更新一起提交亦可，这里先提交实现）**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/collection/collect_plugin/network.py server/apps/cmdb/tests/e2e/test_network_pipeline.py
git commit -m "feat(cmdb): 网络拓扑关系发现替换为归一化/推断/收敛流水线，min_confidence 生效"
```

### Task 10: 更新 e2e 测试套件适配新流水线

**Files:**
- Modify: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/tests/e2e/test_network_pipeline.py`

- [ ] **Step 1: 改写旧 facts 路径测试**

旧的 4 个拓扑测试基于 facts 指标与 ARP 兜底两阶段逻辑，按新语义重写：

1. `test_network_topology_prefers_fact_payload_when_resolvable`（197 行起）：**删除**（facts 指标不再消费；新等价覆盖即 Task 9 的 `test_pipeline_builds_connection_from_lldp_evidence_rows`）。
2. `test_network_topology_falls_back_to_raw_topo_when_facts_absent`（242 行起）：改名 `test_pipeline_infers_connection_from_arp_evidence`，输入只用 `network_topo_info_gauge` 行：两台设备的接口表（IfDescr/IfName/PhysAddress）+ dev1 的 ARP 行指向 dev2 的接口 MAC，断言产出同样的 `interface_connect_interface` 关联（evidence_source=arp 的 inferred 链路）。ARP 行构造：

```python
        topo(dev1, "ARP-IfIndex", "10.0.0.2", "101", "arp"),
        topo(dev1, "ARP-PhysAddress", "10.0.0.2", "0x00aabbccdd02", "arp"),
```

3. `test_network_topology_mixes_resolved_facts_with_raw_fallback_for_unresolved_edges`（314 行起）：改名 `test_pipeline_authoritative_suppresses_arp_inferred_for_same_pair`，输入同时含 LLDP 邻居证据与 ARP 证据（同一对端口），断言只产出一条关联（authoritative 压制 inferred），且 `runner` 上无重复 assos。
4. `test_network_topology_skips_ambiguous_fact_device_lookup_and_keeps_raw_fallback_safe`（501 行起）：改名 `test_pipeline_keeps_ambiguous_remote_unresolved`，构造两台 sysname 相同的远端设备使 LLDP remote 解析歧义，断言**不**产生该边的关联（歧义进入 unresolved，不误连）。
5. `test_network_topology_disabled_keeps_existing_inventory_behavior`（624 行起）：保留，断言的 SQL 改为不含 facts 指标：

```python
    assert sql_calls and sql_calls[0] == (
        "network_system_info_gauge{instance_id='cmdb_7001'} or "
        "network_interfaces_info_gauge{instance_id='cmdb_7001'}"
    )
```

   另有 topo_enabled=True 的 SQL 断言处（如有）改为三个指标：`network_system / network_interfaces / network_topo`。
6. `test_vm_response_includes_topology_fact_metric`（118 行起）：fixture 仍含 facts 指标（agent 仍上报），测试保留但断言放宽为「fixture 合法且 facts 行存在」即可，不再断言 server 消费它。若 fixture schema 校验失败，同步更新 `fixtures`/`schema` 中 network 相关文件加 `group` 标签可选字段。

- [ ] **Step 2: 运行全量 e2e**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 运行 cmdb 全量测试确认无回归**

Run: `cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/ 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/tests/e2e/
git commit -m "test(cmdb): e2e 网络拓扑测试适配新流水线语义"
```

---

## Phase 3：真实设备验证

### Task 11: 四台实验室设备端到端逻辑验证

不依赖部署环境：用增强后的 agent 采集器对 4 台真实设备采集 → 把证据行转成指标行形状 → 喂给 server 适配器 + 流水线 → 对照基线。

**基线（snmp_topo_tool 已验证结论）：**
- authoritative：`10.10.69.245 Ethernet1/0/8 ↔ 10.10.69.247 GigabitEthernet0/0/3`、`10.10.69.248 gi1 ↔ 10.10.69.247 GigabitEthernet0/0/5`
- inferred(fdb+arp, confidence 95)：`10.10.69.247 GigabitEthernet0/0/4 ↔ 10.10.69.246 GigabitEthernet1/0/8`
- 245/246/248 两两之间无链路；unresolved=0；errors=0

**Files:**
- Create: `/Users/luoyang/Desktop/work/code/weopsx/bk-lite/server/apps/cmdb/support-files/verify_topology_lab.py`（手工验证脚本，不进 CI）

- [ ] **Step 1: 工具基线复跑（确认 Phase 0 修复未破坏真实结果）**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool
set -a; source .env.lab; set +a
cat > config.lab.json <<'EOF'
{
  "defaults": {"timeout": 2, "retries": 2, "snmp_port": 161},
  "devices": [
    {"host": "10.10.69.247", "version": "v2c", "community": "${SNMP_COMMUNITY_LAB}"},
    {"host": "10.10.69.245", "version": "v2c", "community": "${SNMP_COMMUNITY_LAB}"},
    {"host": "10.10.69.248", "version": "v2c", "community": "${SNMP_COMMUNITY_LAB}"},
    {"host": "10.10.69.246", "version": "v3", "username": "${SNMP_V3_USER_246}",
     "level": "authPriv", "integrity": "sha", "privacy": "aes",
     "authkey": "${SNMP_V3_AUTHKEY_246}", "privkey": "${SNMP_V3_PRIVKEY_246}"}
  ]
}
EOF
.venv311/bin/python execute.py --config config.lab.json --output result.lab.json --parsed-output parsed_result.lab.json --pretty
.venv311/bin/python -c "
import json
parsed = json.load(open('parsed_result.lab.json'))
print(json.dumps(parsed['summary'], indent=2))
for link in parsed['topology']['authoritative_links'] + parsed['topology']['inferred_links']:
    print(link['source_inst_name'], '<->', link['target_inst_name'], link['evidence_source'], link['confidence'])
"
```

Expected: `authoritative_links=2, inferred_links=1, unresolved_neighbors=0, errors=0`，三条链路与基线一致。
注意：`config.lab.json`、`result.lab.json`、`parsed_result.lab.json`、`.env.lab` **均不提交**。

- [ ] **Step 2: 编写验证脚本**

创建 `server/apps/cmdb/support-files/verify_topology_lab.py`：

```python
"""实验室四台设备的拓扑流水线端到端逻辑验证（手工执行，不进 CI）。

用法:
    cd bk-lite/server
    set -a; source /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/.env.lab; set +a
    uv run python apps/cmdb/support-files/verify_topology_lab.py

依赖 stargazer 的采集器，请先: uv pip install pysnmp==4.4.12 "pyasn1<0.5"
并将 agents/stargazer 加入 PYTHONPATH（脚本内处理）。
"""
import json
import os
import sys

STARGAZER = os.path.join(os.path.dirname(__file__), "../../../../agents/stargazer")
sys.path.insert(0, os.path.abspath(STARGAZER))

from plugins.inputs.network_topo.snmp_topo import SnmpTopo  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from apps.cmdb.collection.collect_plugin.topology.adapter import build_pipeline_aggregate  # noqa: E402
from apps.cmdb.collection.collect_plugin.topology.parse import parse_aggregate_result  # noqa: E402

COMMUNITY = os.environ["SNMP_COMMUNITY_LAB"]
DEVICES = [
    {"host": "10.10.69.247", "version": "v2c", "community": COMMUNITY},
    {"host": "10.10.69.245", "version": "v2c", "community": COMMUNITY},
    {"host": "10.10.69.248", "version": "v2c", "community": COMMUNITY},
    {
        "host": "10.10.69.246", "version": "v3",
        "username": os.environ["SNMP_V3_USER_246"], "level": "authPriv",
        "integrity": "sha", "privacy": "aes",
        "authkey": os.environ["SNMP_V3_AUTHKEY_246"], "privkey": os.environ["SNMP_V3_PRIVKEY_246"],
    },
]

EXPECTED_PAIRS = {
    frozenset({("10.10.69.245", "Ethernet1/0/8"), ("10.10.69.247", "GigabitEthernet0/0/3")}),
    frozenset({("10.10.69.248", "gi1"), ("10.10.69.247", "GigabitEthernet0/0/5")}),
    frozenset({("10.10.69.247", "GigabitEthernet0/0/4"), ("10.10.69.246", "GigabitEthernet1/0/8")}),
}


def main():
    rows = []
    for device in DEVICES:
        host = device["host"]
        print(f"collecting {host} ...")
        records = SnmpTopo({**device, "timeout": 2, "retries": 2}).bulkCmd()
        for record in records:
            rows.append({**record, "instance_id": host})
        print(f"  {len(records)} records")

    parsed = parse_aggregate_result(build_pipeline_aggregate(rows))
    print(json.dumps(parsed["summary"], indent=2))

    actual_pairs = set()
    topology = parsed["topology"]
    for link in topology["authoritative_links"] + topology["inferred_links"]:
        left = (link["source_device"], link["source_inst_name"].split(f"{link['source_device']}-", 1)[-1])
        right = (link["target_device"], (link.get("target_inst_name") or "").split(f"{link['target_device']}-", 1)[-1])
        actual_pairs.add(frozenset({left, right}))
        print(f"{link['relationship_type']:14s} {left} <-> {right} "
              f"[{link['evidence_source']} conf={link['confidence']}]")

    assert parsed["summary"]["authoritative_links"] == 2, parsed["summary"]
    assert parsed["summary"]["inferred_links"] == 1, parsed["summary"]
    assert parsed["summary"]["unresolved_neighbors"] == 0, parsed["summary"]
    assert parsed["summary"]["errors"] == 0, parsed["summary"]
    assert actual_pairs == EXPECTED_PAIRS, f"links mismatch:\n{actual_pairs}\nvs expected\n{EXPECTED_PAIRS}"
    print("\n✅ 与基线一致：2 authoritative + 1 fdb+arp inferred，无误报")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 执行验证**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server
set -a; source /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool/.env.lab; set +a
uv run python apps/cmdb/support-files/verify_topology_lab.py
```

Expected: 末行输出 `✅ 与基线一致`。若设备侧 LLDP 口名/接口命名导致端口名断言差异（如 `gi1` 设备实际 ifName 为 `GigabitEthernet1`），以实际采集为准修正 `EXPECTED_PAIRS` 中的端口名，但**链路对（设备对）必须与基线一致**。

- [ ] **Step 4: Commit**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite
git add server/apps/cmdb/support-files/verify_topology_lab.py
git commit -m "chore(cmdb): 实验室设备拓扑流水线验证脚本"
```

### Task 12: 收尾自检

- [ ] **Step 1: 三仓库全量测试**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx/snmp_topo_tool && .venv311/bin/python -m unittest discover -s tests
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/agents/stargazer && uv run pytest tests/
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite/server && uv run pytest apps/cmdb/tests/
```

Expected: 全部 PASS

- [ ] **Step 2: 对照需求文档验收口径逐条确认**

打开 `spec/requirements/CMDB/20260610.CMDB网络拓扑发现增强.md` 第 3 节，逐条核对：①真实设备回归（Task 11）②CMDB 落库契约不变（Task 9/10 e2e）③降级采集（Task 4）④min_confidence（Task 9，e2e 可补一条 min_confidence=0.95 时 ARP 链路被过滤的断言）⑤过程数据可排查（topology_snapshot）⑥测试迁移与通过。

- [ ] **Step 3: 确认敏感文件未提交**

```bash
cd /Users/luoyang/Desktop/work/code/weopsx && git status --short snmp_topo_tool/ | grep -E "\.env\.lab|config\.lab|result\.lab|parsed_result\.lab" || echo OK-untracked
cd /Users/luoyang/Desktop/work/code/weopsx/bk-lite && git log --oneline -8
```

Expected: 凭据与采集结果文件均未被任何 commit 包含。

---

## 风险与注意事项

1. **pysnmp 版本**：stargazer 现有环境的 pysnmp 版本需确认与 oneliner API 兼容（工具锁 4.4.12）；若 agent 用的是同款 oneliner API（现状如此），无需动依赖。
2. **指标行数增长**：QBRIDGE 全量 FDB 每 MAC 2 行。Out of scope 已声明 v1 不做 agent 侧过滤；若现场指标压力大，后续在 `_format_result` 后按 `FDB-Status/QBRIDGE-FdbStatus != 3` 配对过滤。
3. **e2e 重写的语义差异**：新流水线对「歧义远端」「同设备自环」比旧逻辑更保守（不连），重写断言时以"不误连"为准绳，不要为凑旧断言而放宽。
4. **fixture 漂移**：`tests/e2e/fixtures` 与 schema 若校验失败，只允许"加 group 可选标签"这类增量变更。
