# Historical Superpowers change: 2026-06-05-network-topology-discovery-architecture

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-05-network-topology-discovery-architecture.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add common topology discovery protocols on the current branch, refactor topology responsibilities so Stargazer produces topology facts and CMDB consumes stable facts, and wire the Web UI through task configuration and task-detail display end to end.

**Architecture:** Keep Telegraf and task dispatch unchanged, but change the topology contract that crosses the Stargazer/CMDB boundary. Stargazer should own SNMP MIB collection, LLDP/CDP/FDB parsing, and confidence scoring; CMDB should own topology task configuration, topology fact ingestion, graph persistence, and UI-facing summaries instead of reconstructing topology from raw OID fragments.

**Tech Stack:** Python 3.12, Django/DRF, Sanic, ARQ/Redis, SNMP via pysnmp, Next.js App Router, React, TypeScript, Ant Design, existing CMDB e2e fixtures.

---

## Workload Assessment

| Stream | Scope | Primary files | Effort |
|---|---|---|---:|
| Protocol enrichment | LLDP, CDP, BRIDGE-MIB/FDB, confidence model | `agents/stargazer/plugins/inputs/network_topo/*.py` | 6-8 engineering days |
| Stargazer contract refactor | Convert raw OID rows to stable topology facts payload | `agents/stargazer/plugins/inputs/network/snmp_facts.py`, `agents/stargazer/plugins/inputs/network_topo/*.py` | 3-4 days |
| CMDB ingestion refactor | Consume topology facts, reduce raw OID coupling, preserve graph writes | `server/apps/cmdb/collection/collect_plugin/network.py`, `server/apps/cmdb/node_configs/network/network.py` | 5-6 days |
| Task/API contract | Params validation, protocol selection, task storage | `server/apps/cmdb/serializers/collect_serializer.py`, `server/apps/cmdb/models/collect_model.py`, `web/src/app/cmdb/types/autoDiscovery.ts` | 2-3 days |
| Web configuration UI | Protocol multi-select, fallback strategy, confidence/help text | `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx` | 2-3 days |
| Web result UI | Topology protocol summary, confidence/raw-fact display in task detail | `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/taskDetail.tsx` | 2-3 days |
| End-to-end validation | Existing e2e updates, fixture/schema refresh, type-check/test runs | `server/apps/cmdb/tests/e2e/test_network_pipeline.py`, existing test modules | 3-4 days |

### Delivery Estimate

| Team shape | Estimated calendar time | Notes |
|---|---:|---|
| 1 experienced full-stack engineer | **4-5 weeks** | Includes design drift handling, fixture refresh, and UI polish |
| 2 backend + 1 frontend engineer | **2-2.5 weeks** | Backend split between Stargazer and CMDB; frontend runs in parallel after API contract freezes |
| 1 architect + 2 implementation engineers | **~2 weeks** | Fastest safe path if the architect locks the topology fact contract in week 1 |

## File Structure

### Stargazer

- Create: `agents/stargazer/plugins/inputs/network_topo/protocol_oids.py` — central OID registry for ARP, LLDP, CDP, BRIDGE-MIB/FDB, VLAN-related tables.
- Create: `agents/stargazer/plugins/inputs/network_topo/topology_facts.py` — normalize protocol rows into stable topology fact objects with `source_protocol`, `confidence`, and port identity fields.
- Modify: `agents/stargazer/plugins/inputs/network_topo/snmp_topo.py` — replace hard-coded OID list and raw relationship guessing with protocol-specific collectors plus fact builder.
- Modify: `agents/stargazer/plugins/inputs/network/snmp_facts.py` — publish `network_topology_facts` in `result` when topology is enabled.
- Modify: `agents/stargazer/plugins/inputs/network_topo/plugin.yml` — keep plugin metadata aligned if a separate topology runner stays exposed.
- Test: `agents/stargazer/tests/test_host_collector.py` — extend existing Sanic/collector-style tests with topology fact builder coverage.

### CMDB server

- Modify: `server/apps/cmdb/serializers/collect_serializer.py` — validate new topology params (`topology_protocols`, `topology_fallback_strategy`, `min_confidence`).
- Modify: `server/apps/cmdb/models/collect_model.py` — add helper properties for topology protocol config access.
- Modify: `server/apps/cmdb/node_configs/network/network.py` — send the new topology params to Telegraf/Stargazer headers.
- Modify: `server/apps/cmdb/collection/constants.py` — add metric/fact names for protocol summaries and fact payloads.
- Modify: `server/apps/cmdb/collection/collect_plugin/network.py` — stop reconstructing topology from raw ARP-only rows; consume stable topology facts and build graph edges from them.
- Modify: `server/apps/cmdb/tests/e2e/test_network_pipeline.py` — refresh network pipeline fixture expectations for LLDP/CDP/FDB-backed facts.
- Test: `server/apps/cmdb/tests/test_node_params_multicred.py`, `server/apps/cmdb/tests/test_models.py`, `server/apps/cmdb/tests/test_serializers.py`, `server/apps/cmdb/tests/e2e/test_network_pipeline.py`.

### Web

- Modify: `web/src/app/cmdb/constants/professCollection.ts` — extend SNMP default values and UI copy support.
- Modify: `web/src/app/cmdb/types/autoDiscovery.ts` — type task params/result payloads for topology protocols and fact summary.
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx` — add protocol selection and topology strategy controls.
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/taskDetail.tsx` — render topology fact summary, protocol contribution, and confidence-oriented raw detail.
- Test/Validate: `cd web && pnpm type-check`.

## Task 1: Freeze the topology task contract

**Files:**
- Modify: `server/apps/cmdb/serializers/collect_serializer.py`
- Modify: `server/apps/cmdb/models/collect_model.py`
- Modify: `server/apps/cmdb/node_configs/network/network.py`
- Modify: `web/src/app/cmdb/constants/professCollection.ts`
- Modify: `web/src/app/cmdb/types/autoDiscovery.ts`
- Test: `server/apps/cmdb/tests/test_serializers.py`
- Test: `server/apps/cmdb/tests/test_models.py`
- Test: `server/apps/cmdb/tests/test_node_params_multicred.py`

- [ ] **Step 1: Write the failing serializer/model tests**

```python
def test_network_collect_serializer_accepts_topology_protocol_config():
    serializer = CollectModelSerializer(
        data={
            "name": "topo-snmp",
            "task_type": "snmp",
            "driver_type": "protocol",
            "model_id": "network",
            "timeout": 20,
            "input_method": 0,
            "team": [1],
            "scan_cycle": {"value_type": "cycle", "value": 30},
            "credential": [{"version": "v2", "community": "public", "snmp_port": 161}],
            "params": {
                "has_network_topo": True,
                "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
                "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
                "min_confidence": 0.6,
            },
        }
    )
    assert serializer.is_valid(), serializer.errors
```

```python
def test_collect_model_reads_topology_protocol_helpers():
    model = CollectModels(task_type="snmp", model_id="network", params={"topology_protocols": ["lldp", "arp"]})
    assert model.is_network_topo is False
    assert model.params.get("topology_protocols") == ["lldp", "arp"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_serializers.py apps/cmdb/tests/test_models.py apps/cmdb/tests/test_node_params_multicred.py -v`

Expected: FAIL because the serializer and node params do not yet validate or emit the new topology fields.

- [ ] **Step 3: Implement the contract changes**

```python
# server/apps/cmdb/serializers/collect_serializer.py
def _normalize_topology_protocols(raw_protocols):
    protocols = [str(item).strip().lower() for item in (raw_protocols or []) if str(item).strip()]
    allowed = {"lldp", "cdp", "fdb", "arp"}
    invalid = [item for item in protocols if item not in allowed]
    if invalid:
        raise serializers.ValidationError({"params": f"不支持的拓扑协议: {', '.join(invalid)}"})
    return protocols or ["arp"]
```

```python
# server/apps/cmdb/node_configs/network/network.py
credential_data = {
    "snmp_port": self.credential.get("snmp_port", 161),
    "community": "${" + _community + "}",
    "version": self.credential.get("version", ""),
    "username": self.credential.get("username", ""),
    "level": self.credential.get("level", ""),
    "integrity": self.credential.get("integrity", ""),
    "privacy": self.credential.get("privacy", ""),
    "authkey": "${" + _authkey + "}",
    "privkey": "${" + _privkey + "}",
    "has_network_topo": self.has_network_topo,
    "topology_protocols": self.instance.params.get("topology_protocols", ["arp"]),
    "topology_fallback_strategy": self.instance.params.get(
        "topology_fallback_strategy", "prefer_neighbors_then_fdb_then_arp"
    ),
    "min_confidence": self.instance.params.get("min_confidence", 0.6),
}
```

```ts
// web/src/app/cmdb/types/autoDiscovery.ts
export type TopologyProtocol = 'lldp' | 'cdp' | 'fdb' | 'arp';

export interface NetworkTopologyParams {
  has_network_topo?: boolean;
  topology_protocols?: TopologyProtocol[];
  topology_fallback_strategy?: 'prefer_neighbors_then_fdb_then_arp' | 'strict_neighbors_only';
  min_confidence?: number;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_serializers.py apps/cmdb/tests/test_models.py apps/cmdb/tests/test_node_params_multicred.py -v`

Expected: PASS with serializer validation and node header serialization covering the new topology config.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/serializers/collect_serializer.py \
        server/apps/cmdb/models/collect_model.py \
        server/apps/cmdb/node_configs/network/network.py \
        web/src/app/cmdb/constants/professCollection.ts \
        web/src/app/cmdb/types/autoDiscovery.ts
git commit -m "feat: define topology discovery task contract"
```

### Task 2: Refactor Stargazer topology collection into protocol modules

**Files:**
- Create: `agents/stargazer/plugins/inputs/network_topo/protocol_oids.py`
- Create: `agents/stargazer/plugins/inputs/network_topo/topology_facts.py`
- Modify: `agents/stargazer/plugins/inputs/network_topo/snmp_topo.py`
- Test: `agents/stargazer/tests/test_host_collector.py`

- [ ] **Step 1: Write the failing topology fact tests**

```python
def test_build_topology_fact_prefers_lldp_neighbor():
    fact = build_topology_fact(
        local_device_id="sw-a",
        local_port_name="Gi1/0/1",
        remote_device_id="sw-b",
        remote_port_name="Gi1/0/24",
        source_protocol="lldp",
    )
    assert fact["source_protocol"] == "lldp"
    assert fact["confidence"] == 1.0
```

```python
def test_protocol_oid_registry_contains_neighbor_and_fdb_groups():
    assert "lldp" in TOPOLOGY_PROTOCOL_OIDS
    assert "cdp" in TOPOLOGY_PROTOCOL_OIDS
    assert "fdb" in TOPOLOGY_PROTOCOL_OIDS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "topology_fact or protocol_oid" -v`

Expected: FAIL because the new topology modules do not exist.

- [ ] **Step 3: Add the protocol registry and topology fact builder**

```python
# agents/stargazer/plugins/inputs/network_topo/protocol_oids.py
TOPOLOGY_PROTOCOL_OIDS = {
    "arp": [
        "1.3.6.1.2.1.4.22.1.1",
        "1.3.6.1.2.1.4.22.1.2",
        "1.3.6.1.2.1.4.20.1.1",
        "1.3.6.1.2.1.2.2.1.2",
        "1.3.6.1.2.1.2.2.1.6",
        "1.3.6.1.2.1.31.1.1.1.18",
    ],
    "lldp": [
        "1.0.8802.1.1.2.1.3.7.1.3",
        "1.0.8802.1.1.2.1.3.7.1.4",
        "1.0.8802.1.1.2.1.4.1.1.5",
        "1.0.8802.1.1.2.1.4.1.1.7",
        "1.0.8802.1.1.2.1.4.1.1.8",
        "1.0.8802.1.1.2.1.4.1.1.9",
    ],
    "cdp": [
        "1.3.6.1.4.1.9.9.23.1.2.1.1.4",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
    ],
    "fdb": [
        "1.3.6.1.2.1.17.1.4.1.2",
        "1.3.6.1.2.1.17.4.3.1.1",
        "1.3.6.1.2.1.17.4.3.1.2",
        "1.3.6.1.2.1.17.7.1.2.2.1.2",
    ],
}
```

```python
# agents/stargazer/plugins/inputs/network_topo/topology_facts.py
def build_topology_fact(*, local_device_id, local_port_name, remote_device_id, remote_port_name, source_protocol):
    base_confidence = {"lldp": 1.0, "cdp": 0.95, "fdb": 0.75, "arp": 0.5}[source_protocol]
    return {
        "local_device_id": local_device_id,
        "local_port_name": local_port_name,
        "remote_device_id": remote_device_id,
        "remote_port_name": remote_port_name,
        "source_protocol": source_protocol,
        "confidence": base_confidence,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "topology_fact or protocol_oid" -v`

Expected: PASS with the registry and fact builder covered.

- [ ] **Step 5: Commit**

```bash
git add agents/stargazer/plugins/inputs/network_topo/protocol_oids.py \
        agents/stargazer/plugins/inputs/network_topo/topology_facts.py \
        agents/stargazer/plugins/inputs/network_topo/snmp_topo.py \
        agents/stargazer/tests/test_host_collector.py
git commit -m "feat: extract topology protocol registry"
```

### Task 3: Implement LLDP and CDP neighbor parsing

**Files:**
- Modify: `agents/stargazer/plugins/inputs/network_topo/snmp_topo.py`
- Modify: `agents/stargazer/plugins/inputs/network/snmp_facts.py`
- Test: `agents/stargazer/tests/test_host_collector.py`

- [ ] **Step 1: Write the failing neighbor-protocol tests**

```python
def test_snmp_topo_builds_lldp_neighbor_facts():
    topo = SnmpTopo({"host": "10.0.0.1", "version": "v2", "community": "public"})
    rows = [
        {"tag": "LLDP-LocalPortId", "ifindex": "10101", "val": "Gi1/0/1"},
        {"tag": "LLDP-RemoteSysName", "ifindex": "10101", "val": "sw-b"},
        {"tag": "LLDP-RemotePortId", "ifindex": "10101", "val": "Gi1/0/24"},
    ]
    facts = topo.build_topology_facts(rows, enabled_protocols=["lldp"])
    assert facts[0]["source_protocol"] == "lldp"
```

```python
def test_snmp_topo_builds_cdp_neighbor_facts():
    topo = SnmpTopo({"host": "10.0.0.1", "version": "v2", "community": "public"})
    rows = [
        {"tag": "CDP-CacheIfIndex", "ifindex": "12", "val": "12"},
        {"tag": "CDP-CacheDeviceId", "ifindex": "12", "val": "dist-sw-01"},
        {"tag": "CDP-CacheDevicePort", "ifindex": "12", "val": "Ten1/1/48"},
    ]
    facts = topo.build_topology_facts(rows, enabled_protocols=["cdp"])
    assert facts[0]["source_protocol"] == "cdp"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "lldp_neighbor or cdp_neighbor" -v`

Expected: FAIL because `snmp_topo.py` does not parse neighbor MIB tables yet.

- [ ] **Step 3: Implement LLDP/CDP collection and fact generation**

```python
# agents/stargazer/plugins/inputs/network_topo/snmp_topo.py
def build_topology_facts(self, snmp_rows, enabled_protocols):
    facts = []
    if "lldp" in enabled_protocols:
        facts.extend(self._build_lldp_facts(snmp_rows))
    if "cdp" in enabled_protocols:
        facts.extend(self._build_cdp_facts(snmp_rows))
    return facts
```

```python
# agents/stargazer/plugins/inputs/network/snmp_facts.py
if self.has_network_topo:
    topo_collector = SnmpTopo(self.kwargs)
    model_data["network_topology_facts"] = topo_collector.list_topology_facts(
        enabled_protocols=self.kwargs.get("topology_protocols", ["arp"])
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "lldp_neighbor or cdp_neighbor" -v`

Expected: PASS with LLDP/CDP facts emitted from SNMP rows.

- [ ] **Step 5: Commit**

```bash
git add agents/stargazer/plugins/inputs/network_topo/snmp_topo.py \
        agents/stargazer/plugins/inputs/network/snmp_facts.py \
        agents/stargazer/tests/test_host_collector.py
git commit -m "feat: add lldp and cdp topology discovery"
```

### Task 4: Add FDB fallback and confidence-aware protocol fusion

**Files:**
- Modify: `agents/stargazer/plugins/inputs/network_topo/snmp_topo.py`
- Modify: `agents/stargazer/plugins/inputs/network_topo/topology_facts.py`
- Test: `agents/stargazer/tests/test_host_collector.py`

- [ ] **Step 1: Write the failing FDB/confidence tests**

```python
def test_topology_fact_builder_uses_fdb_when_neighbor_protocols_missing():
    facts = merge_topology_facts(
        lldp_facts=[],
        cdp_facts=[],
        fdb_facts=[{"local_device_id": "sw-a", "local_port_name": "Gi1/0/2", "remote_device_id": "sw-b"}],
        arp_facts=[],
    )
    assert facts[0]["source_protocol"] == "fdb"
    assert facts[0]["confidence"] == 0.75
```

```python
def test_topology_fact_builder_keeps_arp_as_last_fallback():
    facts = merge_topology_facts(
        lldp_facts=[],
        cdp_facts=[],
        fdb_facts=[],
        arp_facts=[
            {
                "local_device_id": "sw-a",
                "local_port_name": "Gi1/0/3",
                "remote_device_id": "sw-c",
                "remote_port_name": "unknown",
                "source_protocol": "arp",
                "confidence": 0.5,
            }
        ],
    )
    assert facts[-1]["source_protocol"] == "arp"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "fdb_when_neighbor_protocols_missing or arp_as_last_fallback" -v`

Expected: FAIL because FDB facts and protocol merge policy do not exist.

- [ ] **Step 3: Implement FDB parsing and merge order**

```python
# agents/stargazer/plugins/inputs/network_topo/topology_facts.py
def merge_topology_facts(*, lldp_facts, cdp_facts, fdb_facts, arp_facts):
    ordered = [*lldp_facts, *cdp_facts, *fdb_facts, *arp_facts]
    dedup = {}
    for fact in ordered:
        key = (fact["local_device_id"], fact["local_port_name"], fact["remote_device_id"], fact.get("remote_port_name"))
        dedup.setdefault(key, fact)
    return list(dedup.values())
```

```python
# agents/stargazer/plugins/inputs/network_topo/snmp_topo.py
def list_topology_facts(self, enabled_protocols):
    rows = self.bulkCmd()
    return merge_topology_facts(
        lldp_facts=self._build_lldp_facts(rows) if "lldp" in enabled_protocols else [],
        cdp_facts=self._build_cdp_facts(rows) if "cdp" in enabled_protocols else [],
        fdb_facts=self._build_fdb_facts(rows) if "fdb" in enabled_protocols else [],
        arp_facts=self._build_arp_facts(rows) if "arp" in enabled_protocols else [],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "fdb_when_neighbor_protocols_missing or arp_as_last_fallback" -v`

Expected: PASS with confidence-aware protocol fusion.

- [ ] **Step 5: Commit**

```bash
git add agents/stargazer/plugins/inputs/network_topo/snmp_topo.py \
        agents/stargazer/plugins/inputs/network_topo/topology_facts.py \
        agents/stargazer/tests/test_host_collector.py
git commit -m "feat: add fdb fallback for topology facts"
```

### Task 5: Refactor CMDB to ingest topology facts instead of raw ARP inference

**Files:**
- Modify: `server/apps/cmdb/collection/constants.py`
- Modify: `server/apps/cmdb/collection/collect_plugin/network.py`
- Modify: `server/apps/cmdb/collection/plugins/community/network/plugins.py`
- Test: `server/apps/cmdb/tests/e2e/test_network_pipeline.py`

- [ ] **Step 1: Write the failing CMDB topology ingestion tests**

```python
@pytest.mark.django_db
def test_network_pipeline_uses_topology_fact_payload(monkeypatch):
    vm_resp = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"__name__": "network_topology_facts_info_gauge", "instance_id": "cmdb_7001", "source_protocol": "lldp", "local_device_id": "sw-a", "local_port_name": "Gi1/0/1", "remote_device_id": "sw-b", "remote_port_name": "Gi1/0/24"}, "value": [1, "1"]},
            ],
        },
    }
    monkeypatch.setattr("apps.cmdb.collection.query_vm.Collection.query", lambda self, sql, timeout=60: vm_resp)
    from types import SimpleNamespace

    fake_task = SimpleNamespace(id=7001, is_network_topo=True, instances=[])
    monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(CollectNetworkMetrics, "model_id", property(lambda self: "network"))

    runner = CollectNetworkMetrics(inst_name="snmp-task-01", inst_id=70001, task_id=7001)
    runner.run()
    assert runner.result["interface"][0]["assos"][0]["asst_id"] == "connect"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py -v`

Expected: FAIL because CMDB only understands `network_topo_info_gauge` ARP-style rows.

- [ ] **Step 3: Implement topology fact ingestion**

```python
# server/apps/cmdb/collection/constants.py
NETWORK_COLLECT = [
    "network_system_info_gauge",
    "network_interfaces_info_gauge",
    "network_topology_facts_info_gauge",
]
```

```python
# server/apps/cmdb/collection/collect_plugin/network.py
def format_metrics(self):
    topology_facts = self.collection_metrics_dict.pop("network_topology_facts_info_gauge", [])
    if self.is_topo:
        self.add_interface_assos(self.build_associations_from_facts(topology_facts))
```

```python
def build_interface_inst_name(self, device_id, port_name):
    device = self.instance_id_map[device_id]
    return f"{self.set_inst_name(device)}-{port_name}"
```

```python
def build_associations_from_facts(self, facts):
    return [
        {
            "source_inst_name": self.build_interface_inst_name(fact["local_device_id"], fact["local_port_name"]),
            "target_inst_name": self.build_interface_inst_name(fact["remote_device_id"], fact["remote_port_name"]),
            "source_protocol": fact.get("source_protocol", "arp"),
            "confidence": fact.get("confidence", 0),
            "model_id": "interface",
            "asst_id": "connect",
            "model_asst_id": "interface_connect_interface",
        }
        for fact in facts
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py -v`

Expected: PASS with graph associations sourced from stable topology facts.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/collection/constants.py \
        server/apps/cmdb/collection/collect_plugin/network.py \
        server/apps/cmdb/collection/plugins/community/network/plugins.py \
        server/apps/cmdb/tests/e2e/test_network_pipeline.py
git commit -m "refactor: ingest topology facts in cmdb"
```

### Task 6: Add topology protocol configuration to the SNMP task UI

**Files:**
- Modify: `web/src/app/cmdb/constants/professCollection.ts`
- Modify: `web/src/app/cmdb/types/autoDiscovery.ts`
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx`
- Validate: `cd web && pnpm type-check`

- [ ] **Step 1: Add the failing UI type usage**

```ts
const initialFormValues = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.INTERVAL,
  intervalValue: 30,
  enterType: ENTER_TYPE.AUTOMATIC,
  version: 'v2',
  snmp_port: '161',
  timeout: 20,
  level: 'authNoPriv',
  integrity: 'sha',
  privacy: 'aes',
  hasNetworkTopo: true,
  cleanupStrategy: 'no_cleanup',
  cleanupDays: 3,
  topologyProtocols: ['lldp', 'cdp', 'fdb', 'arp'],
  topologyFallbackStrategy: 'prefer_neighbors_then_fdb_then_arp',
  minConfidence: 0.6,
  credentialPool: [{ version: 'v2', snmp_port: '161' }],
};
```

```ts
return Object.assign({}, baseData, {
  params: {
    has_network_topo: values.hasNetworkTopo ?? true,
    topology_protocols: values.topologyProtocols,
    topology_fallback_strategy: values.topologyFallbackStrategy,
    min_confidence: values.minConfidence,
  },
});
```

- [ ] **Step 2: Run type-check to verify it fails**

Run: `cd web && pnpm type-check`

Expected: FAIL because the form values and task types do not yet include the topology protocol fields.

- [ ] **Step 3: Implement the UI controls**

```tsx
<Form.Item label={t('Collection.SNMPTask.topologyProtocols')} name="topologyProtocols">
  <Checkbox.Group
    options={[
      { label: 'LLDP', value: 'lldp' },
      { label: 'CDP', value: 'cdp' },
      { label: 'FDB', value: 'fdb' },
      { label: t('Collection.SNMPTask.arpFallback'), value: 'arp' },
    ]}
  />
</Form.Item>

<Form.Item label={t('Collection.SNMPTask.minConfidence')} name="minConfidence">
  <Slider min={0.1} max={1} step={0.05} />
</Form.Item>

import { Checkbox, Form, Slider, Spin, Switch } from 'antd';
```

- [ ] **Step 4: Run type-check to verify it passes**

Run: `cd web && pnpm type-check`

Expected: PASS with the SNMP task form and types aligned.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/cmdb/constants/professCollection.ts \
        web/src/app/cmdb/types/autoDiscovery.ts \
        web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx
git commit -m "feat: expose topology protocol selection in ui"
```

### Task 7: Expose topology fact summaries in task detail UI

**Files:**
- Modify: `web/src/app/cmdb/types/autoDiscovery.ts`
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/taskDetail.tsx`
- Validate: `cd web && pnpm type-check`

- [ ] **Step 1: Add the failing task-detail rendering expectation**

```ts
const topologySummary = detailData.raw_data?.data?.find(
  (item: any) => item.source_protocol && item.confidence
);
expect(topologySummary?.source_protocol).toBe('lldp');
```

- [ ] **Step 2: Run type-check to verify the shape is missing**

Run: `cd web && pnpm type-check`

Expected: FAIL because raw detail payload typing does not include topology fact fields.

- [ ] **Step 3: Render protocol/confidence-oriented detail**

```tsx
<Descriptions.Item label={t('Collection.taskDetail.topologyProtocols')}>
  {Array.from(new Set(rawData.map((item: any) => item.source_protocol).filter(Boolean))).join(', ') || '--'}
</Descriptions.Item>
<Descriptions.Item label={t('Collection.taskDetail.topologyConfidence')}>
  {rawData.length
    ? rawData
        .reduce((max: number, item: any) => Math.max(max, Number(item.confidence || 0)), 0)
        .toFixed(2)
    : '--'}
</Descriptions.Item>
```

```tsx
const normalizedValue =
  typeof value === 'number' && key === 'confidence' ? value.toFixed(2) : String(value || '--');
```

- [ ] **Step 4: Run type-check to verify it passes**

Run: `cd web && pnpm type-check`

Expected: PASS with task detail rendering topology facts safely.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/cmdb/types/autoDiscovery.ts \
        web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/taskDetail.tsx
git commit -m "feat: show topology fact summaries in task detail"
```

### Task 8: Run end-to-end validation and refresh operator-facing docs

**Files:**
- Modify: `server/apps/cmdb/tests/e2e/test_network_pipeline.py`
- Modify: `server/apps/cmdb/tests/e2e/schemas/network/03_vm_metrics.schema.json`
- Modify: `server/apps/cmdb/collection/CMDB配置采集插件开发指南.md`
- Modify: `agents/stargazer/README.md`
- Validate: existing repo commands only

- [ ] **Step 1: Extend the failing e2e fixture/schema assertions**

```python
def test_network_device_pipeline_includes_protocol_backed_topology_facts(load_fixture, monkeypatch):
    vm_resp = load_fixture("network/03_vm_metrics_response.json")
    schema = load_schema("network/03_vm_metrics.schema.json")
    jsonschema.validate(vm_resp, schema)
    assert any(
        item["metric"]["__name__"] == "network_topology_facts_info_gauge"
        for item in vm_resp["data"]["result"]
    )
```

- [ ] **Step 2: Run the failing validation**

Run: `cd server && uv run pytest apps/cmdb/tests/e2e/test_network_pipeline.py -v`

Expected: FAIL until fixtures, schema, and CMDB/Stargazer contract are aligned.

- [ ] **Step 3: Refresh docs and schemas**

```json
{
  "__name__": {
    "type": "string",
    "enum": [
      "network_system_info_gauge",
      "network_interfaces_info_gauge",
      "network_topology_facts_info_gauge"
    ]
  }
}
```

```md
- topology_protocols: `lldp`, `cdp`, `fdb`, `arp`
- topology_fallback_strategy: `prefer_neighbors_then_fdb_then_arp` or `strict_neighbors_only`
- network_topology_facts: stable topology facts emitted by Stargazer and consumed by CMDB
```

- [ ] **Step 4: Run the validation suite**

Run: `cd agents/stargazer && uv run pytest tests/test_host_collector.py -k "topology" -v && cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server && uv run pytest apps/cmdb/tests/test_serializers.py apps/cmdb/tests/test_models.py apps/cmdb/tests/test_node_params_multicred.py apps/cmdb/tests/e2e/test_network_pipeline.py -v && cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/web && pnpm type-check`

Expected: PASS with Stargazer topology collectors, CMDB ingestion, and Web UI types all aligned.

- [ ] **Step 5: Commit**

```bash
git add agents/stargazer/README.md \
        server/apps/cmdb/tests/e2e/test_network_pipeline.py \
        server/apps/cmdb/tests/e2e/schemas/network/03_vm_metrics.schema.json \
        server/apps/cmdb/collection/CMDB配置采集插件开发指南.md
git commit -m "docs: describe topology discovery contract"
```

## Self-Review

- **Spec coverage:** The plan covers protocol enrichment (LLDP/CDP/FDB/ARP), Stargazer-side topology fact production, CMDB ingestion refactor, Web task configuration, Web task-detail display, and end-to-end validation.
- **Placeholder scan:** Removed the placeholder markers and replaced them with concrete OIDs, test bodies, helper names, and object literals.
- **Type consistency:** The same parameter names are used throughout: `topology_protocols`, `topology_fallback_strategy`, `min_confidence`, and `network_topology_facts`.
