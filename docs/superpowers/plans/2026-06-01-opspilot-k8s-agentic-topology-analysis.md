# OpsPilot K8s Agentic 拓扑分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a K8s-topic-only agentic topology analysis flow that scales beyond large workload counts by moving from single-context full-cluster analysis to snapshot, graph, subgraph, and structured-findings synthesis.

**Architecture:** Add a dedicated Kubernetes topology pipeline inside the OpsPilot K8s toolkit instead of changing the generic agent runtime. The implementation introduces snapshot, graph, partition, and memory helpers plus new K8s-only tools and prompt rules so the agent can plan with graph summaries, inspect bounded subgraphs, persist findings externally, and synthesize the final report without reloading the whole cluster into one context.

**Tech Stack:** Python 3.12, Django test suite, LangChain tool decorators, Kubernetes Python client, pytest, existing OpsPilot K8s chatflow prompts.

---

## File Structure

### New files

- `server/apps/opspilot/metis/llm/tools/kubernetes/topology_schema.py`  
  Pydantic models and typed dict helpers for snapshot metadata, graph nodes, graph edges, subgraph payloads, and structured local findings.

- `server/apps/opspilot/metis/llm/tools/kubernetes/topology_snapshot.py`  
  Kubernetes snapshot builder that collects workload, pod, node, service, ingress, PVC/PV, config, autoscaling, and event metadata into one versioned payload.

- `server/apps/opspilot/metis/llm/tools/kubernetes/topology_graph.py`  
  Graph builder plus token-budget-aware partitioner that emits subgraphs and `bridge_refs`.

- `server/apps/opspilot/metis/llm/tools/kubernetes/topology_memory.py`  
  In-process structured memory store keyed by `snapshot_id` for subgraph findings and synthesis inputs.

- `server/apps/opspilot/metis/llm/tools/kubernetes/topology_tools.py`  
  Tool entrypoints the K8s topic agent will actually use: build snapshot, summarize graph, fetch bounded subgraph evidence, record findings, list findings, and synthesize the final dataset for the formatter.

- `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`  
  Unit tests for schema, snapshot shaping, graph edges, partitioning, budget enforcement, and finding persistence.

- `server/apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py`  
  ReAct-style behavior tests proving the K8s topic prompt steers the agent to graph-first analysis and bounded evidence reads.

### Modified files

- `server/apps/opspilot/metis/llm/tools/kubernetes/__init__.py`  
  Export topology helpers and include them in the full K8s toolkit metadata.

- `server/apps/opspilot/metis/llm/tools/kubernetes_data_collection.py`  
  Keep the K8s-topic-restricted toolkit narrow, but add the new topology analysis tools needed by the built-in K8s chatflow.

- `server/apps/opspilot/management/chatflow_data/k8s/check.txt`  
  Rewrite the topic prompt so the agent must build topology first, inspect subgraphs second, persist local findings, and only then synthesize the final report.

- `server/apps/opspilot/management/chatflow_data/k8s/format.txt`  
  Align the formatter prompt with the new `topology_analysis_package` output rather than raw recollection.

- `server/apps/opspilot/tests/test_kubernetes_data_collection_tools.py`  
  Update toolkit metadata and built-in chatflow assertions to cover the new topology tools and prompt guardrails.

- `server/apps/opspilot/tests/test_k8s_scenario_e2e.py`  
  Extend the real-cluster scenario script so it exercises the topology flow on shared-node / shared-service style cases.

## Scope check

This spec is one subsystem: a K8s-topic-only execution pipeline. It touches multiple files, but they all serve one path and can ship behind the existing K8s topic without splitting into separate plans.

### Task 1: Lock the topology schema and graph contracts with failing tests

**Files:**
- Create: `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`
- Create: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_schema.py`

- [ ] **Step 1: Write the failing schema tests**

Add tests that define the exact structure expected by later tasks:

```python
import pytest


def test_topology_snapshot_schema_exposes_versioned_collections():
    from apps.opspilot.metis.llm.tools.kubernetes.topology_schema import TopologySnapshot

    snapshot = TopologySnapshot(
        snapshot_id="snap-1",
        cluster_name="prod-a",
        generated_at="2026-06-01T00:00:00Z",
        resources={"deployments": [], "pods": [], "nodes": [], "services": []},
        stats={"deployment_count": 0, "pod_count": 0},
    )

    assert snapshot.snapshot_id == "snap-1"
    assert snapshot.resources["deployments"] == []
    assert snapshot.stats["deployment_count"] == 0


def test_local_finding_schema_requires_bridge_refs_and_evidence_refs():
    from apps.opspilot.metis.llm.tools.kubernetes.topology_schema import LocalFinding

    finding = LocalFinding(
        snapshot_id="snap-1",
        subgraph_id="sg-1",
        issues=[
            {
                "issue_id": "missing-liveness",
                "severity": "high",
                "summary": "Container missing liveness probe",
                "impacted_resources": ["Deployment/api"],
                "evidence_refs": ["deployment:default/api"],
                "bridge_refs": ["node:worker-a"],
                "fix_suggestions": ["Add HTTP liveness probe"],
                "confidence": 0.82,
            }
        ],
    )

    assert finding.issues[0]["bridge_refs"] == ["node:worker-a"]
```

- [ ] **Step 2: Run the schema test file and verify it fails**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py -v
```

Expected: `ModuleNotFoundError` for `topology_schema`.

- [ ] **Step 3: Create the minimal schema models**

Start with focused models that later tasks can reuse directly:

```python
from pydantic import BaseModel, Field


class TopologySnapshot(BaseModel):
    snapshot_id: str
    cluster_name: str
    generated_at: str
    resources: dict[str, list[dict]]
    stats: dict[str, int] = Field(default_factory=dict)


class TopologySubgraph(BaseModel):
    snapshot_id: str
    subgraph_id: str
    node_ids: list[str]
    edge_ids: list[str]
    bridge_refs: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)


class LocalFinding(BaseModel):
    snapshot_id: str
    subgraph_id: str
    issues: list[dict]
```

- [ ] **Step 4: Re-run the schema tests and verify they pass**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py -v
```

Expected: both new schema tests pass.

- [ ] **Step 5: Commit the schema contract**

```bash
git add server/apps/opspilot/metis/llm/tools/kubernetes/topology_schema.py server/apps/opspilot/tests/test_kubernetes_topology_tools.py
git commit -m "test: lock k8s topology schema contracts"
```

### Task 2: Build snapshot collection with K8s-topic-only data shaping

**Files:**
- Modify: `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`
- Create: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_snapshot.py`

- [ ] **Step 1: Add failing snapshot tests that reuse existing Kubernetes API patterns**

Extend the test file with a snapshot builder contract:

```python
def test_build_topology_snapshot_collects_related_resource_sets(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.topology_snapshot import build_topology_snapshot

    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.topology_snapshot._collect_resources",
        return_value={
            "deployments": [{"namespace": "default", "name": "api"}],
            "pods": [{"namespace": "default", "name": "api-7d8c"}],
            "nodes": [{"name": "worker-a"}],
            "services": [{"namespace": "default", "name": "api"}],
            "events": [{"reason": "Unhealthy"}],
        },
    )
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.topology_snapshot.get_current_cluster_name",
        return_value="prod-a",
    )

    snapshot = build_topology_snapshot(namespace="default")

    assert snapshot.cluster_name == "prod-a"
    assert snapshot.resources["deployments"][0]["name"] == "api"
    assert snapshot.stats["deployment_count"] == 1
```

- [ ] **Step 2: Run the snapshot test and verify it fails**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py::test_build_topology_snapshot_collects_related_resource_sets -v
```

Expected: `ModuleNotFoundError` for `topology_snapshot`.

- [ ] **Step 3: Implement the minimal snapshot builder**

Create a collector that stays inside the K8s topic domain and emits a versioned payload:

```python
from datetime import datetime, timezone
from uuid import uuid4

from apps.opspilot.metis.llm.tools.kubernetes.topology_schema import TopologySnapshot
from apps.opspilot.metis.llm.tools.kubernetes.utils import get_current_cluster_name, prepare_context


def build_topology_snapshot(namespace=None, config=None):
    prepare_context(config)
    resources = _collect_resources(namespace=namespace)
    return TopologySnapshot(
        snapshot_id=f"snap-{uuid4().hex}",
        cluster_name=get_current_cluster_name(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        resources=resources,
        stats={
            "deployment_count": len(resources.get("deployments", [])),
            "pod_count": len(resources.get("pods", [])),
            "node_count": len(resources.get("nodes", [])),
            "service_count": len(resources.get("services", [])),
        },
    )
```

- [ ] **Step 4: Add resource shaping that captures the relationships later tasks need**

Use small, deterministic records rather than full YAML dumps:

```python
def _shape_pod(pod):
    return {
        "id": f"pod:{pod.metadata.namespace}/{pod.metadata.name}",
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "node_name": pod.spec.node_name,
        "owner_refs": [
            {"kind": ref.kind, "name": ref.name, "uid": ref.uid}
            for ref in (pod.metadata.owner_references or [])
        ],
        "labels": pod.metadata.labels or {},
        "config_refs": _extract_config_refs(pod),
    }
```

- [ ] **Step 5: Re-run the snapshot-focused tests**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py -v
```

Expected: schema and snapshot tests pass together.

- [ ] **Step 6: Commit the snapshot layer**

```bash
git add server/apps/opspilot/metis/llm/tools/kubernetes/topology_snapshot.py server/apps/opspilot/tests/test_kubernetes_topology_tools.py
git commit -m "feat: add k8s topology snapshot builder"
```

### Task 3: Add graph construction and token-budget-aware partitioning

**Files:**
- Modify: `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`
- Create: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_graph.py`

- [ ] **Step 1: Add failing tests for graph edges and subgraph partitioning**

Lock the expected cross-resource relationships and bridge handling:

```python
def test_build_topology_graph_connects_workload_service_and_node():
    from apps.opspilot.metis.llm.tools.kubernetes.topology_graph import build_topology_graph
    from apps.opspilot.metis.llm.tools.kubernetes.topology_schema import TopologySnapshot

    snapshot = TopologySnapshot(
        snapshot_id="snap-1",
        cluster_name="prod-a",
        generated_at="2026-06-01T00:00:00Z",
        resources={
            "deployments": [{"id": "deployment:default/api", "namespace": "default", "name": "api", "selector": {"app": "api"}}],
            "pods": [{"id": "pod:default/api-1", "namespace": "default", "name": "api-1", "node_name": "worker-a", "labels": {"app": "api"}}],
            "nodes": [{"id": "node:worker-a", "name": "worker-a"}],
            "services": [{"id": "service:default/api", "namespace": "default", "name": "api", "selector": {"app": "api"}}],
        },
        stats={},
    )

    graph = build_topology_graph(snapshot)

    assert ("deployment:default/api", "pod:default/api-1") in graph["adjacency"]
    assert ("pod:default/api-1", "node:worker-a") in graph["adjacency"]
    assert ("service:default/api", "deployment:default/api") in graph["adjacency"]


def test_partition_graph_splits_on_budget_and_emits_bridge_refs():
    from apps.opspilot.metis.llm.tools.kubernetes.topology_graph import partition_topology_graph

    graph = {
        "snapshot_id": "snap-1",
        "nodes": {
            "deployment:default/api": {"estimated_tokens": 180},
            "pod:default/api-1": {"estimated_tokens": 180},
            "node:worker-a": {"estimated_tokens": 180},
        },
        "adjacency": [
            ("deployment:default/api", "pod:default/api-1"),
            ("pod:default/api-1", "node:worker-a"),
        ],
    }

    parts = partition_topology_graph(graph, max_tokens_per_subgraph=250)

    assert len(parts) == 2
    assert any("node:worker-a" in part.bridge_refs for part in parts)
```

- [ ] **Step 2: Run the new graph tests and verify they fail**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py::test_build_topology_graph_connects_workload_service_and_node -v
```

Expected: `ModuleNotFoundError` for `topology_graph`.

- [ ] **Step 3: Implement graph construction with explicit K8s relationship edges**

Create a focused graph builder instead of a generic cross-domain graph service:

```python
def build_topology_graph(snapshot):
    nodes = {}
    adjacency = []

    for deployment in snapshot.resources.get("deployments", []):
        nodes[deployment["id"]] = {"kind": "deployment", "estimated_tokens": 180, "data": deployment}

    for pod in snapshot.resources.get("pods", []):
        nodes[pod["id"]] = {"kind": "pod", "estimated_tokens": 180, "data": pod}
        if pod.get("node_name"):
            adjacency.append((pod["id"], f"node:{pod['node_name']}"))

    for service in snapshot.resources.get("services", []):
        nodes[service["id"]] = {"kind": "service", "estimated_tokens": 120, "data": service}
        for deployment in snapshot.resources.get("deployments", []):
            if _selector_matches(service.get("selector", {}), deployment.get("selector", {})):
                adjacency.append((service["id"], deployment["id"]))

    return {"snapshot_id": snapshot.snapshot_id, "nodes": nodes, "adjacency": adjacency}
```

- [ ] **Step 4: Implement the partitioner with `bridge_refs` and bounded evidence**

Keep partitions token-aware and relationship-aware:

```python
from uuid import uuid4

from apps.opspilot.metis.llm.tools.kubernetes.topology_schema import TopologySubgraph


def partition_topology_graph(graph, max_tokens_per_subgraph=1800):
    partitions = []
    current_nodes = []
    current_tokens = 0

    for node_id, node_payload in graph["nodes"].items():
        estimated = node_payload.get("estimated_tokens", 0)
        if current_nodes and current_tokens + estimated > max_tokens_per_subgraph:
            partitions.append(_build_partition(graph, current_nodes))
            current_nodes = []
            current_tokens = 0
        current_nodes.append(node_id)
        current_tokens += estimated

    if current_nodes:
        partitions.append(_build_partition(graph, current_nodes))
    return partitions


def _build_partition(graph, node_ids):
    node_set = set(node_ids)
    edge_ids = []
    bridge_refs = []
    for source, target in graph["adjacency"]:
        if source in node_set and target in node_set:
            edge_ids.append(f"{source}->{target}")
        elif source in node_set or target in node_set:
            bridge_refs.append(target if source in node_set else source)

    return TopologySubgraph(
        snapshot_id=graph["snapshot_id"],
        subgraph_id=f"sg-{uuid4().hex}",
        node_ids=node_ids,
        edge_ids=edge_ids,
        bridge_refs=sorted(set(bridge_refs)),
        summary={"node_count": len(node_ids), "bridge_count": len(set(bridge_refs))},
    )
```

- [ ] **Step 5: Re-run the topology unit tests**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py -v
```

Expected: graph and partitioning assertions pass.

- [ ] **Step 6: Commit the graph layer**

```bash
git add server/apps/opspilot/metis/llm/tools/kubernetes/topology_graph.py server/apps/opspilot/tests/test_kubernetes_topology_tools.py
git commit -m "feat: add k8s topology graph partitioning"
```

### Task 4: Add structured findings memory and K8s-only topology tools

**Files:**
- Modify: `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`
- Create: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_memory.py`
- Create: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_tools.py`
- Modify: `server/apps/opspilot/metis/llm/tools/kubernetes/__init__.py`
- Modify: `server/apps/opspilot/metis/llm/tools/kubernetes_data_collection.py`

- [ ] **Step 1: Add failing tests for finding persistence and toolkit exposure**

Define the tool contract before implementing it:

```python
import json


def test_record_topology_findings_persists_by_snapshot_and_subgraph():
    from apps.opspilot.metis.llm.tools.kubernetes.topology_memory import reset_topology_memory
    from apps.opspilot.metis.llm.tools.kubernetes.topology_tools import list_k8s_topology_findings, record_k8s_topology_findings

    reset_topology_memory()
    record_k8s_topology_findings.invoke(
        {
            "snapshot_id": "snap-1",
            "subgraph_id": "sg-1",
            "issues": [
                {
                    "issue_id": "missing-readiness",
                    "severity": "high",
                    "summary": "Missing readiness probe",
                    "impacted_resources": ["Deployment/api"],
                    "evidence_refs": ["deployment:default/api"],
                    "bridge_refs": ["service:default/api"],
                    "fix_suggestions": ["Add readiness probe"],
                    "confidence": 0.7,
                }
            ],
        }
    )

    payload = json.loads(list_k8s_topology_findings.invoke({"snapshot_id": "snap-1"}))
    assert payload["finding_count"] == 1
    assert payload["findings"][0]["subgraph_id"] == "sg-1"
```

- [ ] **Step 2: Run the new finding test and verify it fails**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py::test_record_topology_findings_persists_by_snapshot_and_subgraph -v
```

Expected: missing `topology_memory` or `topology_tools`.

- [ ] **Step 3: Implement a minimal external memory helper**

Use a focused in-process store first; it keeps the K8s topic isolated and testable:

```python
from collections import defaultdict

_TOPOLOGY_FINDINGS = defaultdict(list)


def reset_topology_memory():
    _TOPOLOGY_FINDINGS.clear()


def store_finding(snapshot_id, finding):
    _TOPOLOGY_FINDINGS[snapshot_id].append(finding)


def get_findings(snapshot_id):
    return list(_TOPOLOGY_FINDINGS.get(snapshot_id, []))
```

- [ ] **Step 4: Implement the tool entrypoints with budget and coverage metadata**

Expose the graph-first tool flow the prompt will enforce:

```python
import json

from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.kubernetes.topology_graph import build_topology_graph, partition_topology_graph
from apps.opspilot.metis.llm.tools.kubernetes.topology_memory import get_findings, store_finding
from apps.opspilot.metis.llm.tools.kubernetes.topology_snapshot import build_topology_snapshot


@tool()
def build_k8s_topology_snapshot(namespace=None, config=None):
    snapshot = build_topology_snapshot(namespace=namespace, config=config)
    graph = build_topology_graph(snapshot)
    partitions = partition_topology_graph(graph)
    return json.dumps(
        {
            "snapshot_id": snapshot.snapshot_id,
            "cluster_name": snapshot.cluster_name,
            "stats": snapshot.stats,
            "subgraphs": [
                {"subgraph_id": part.subgraph_id, "node_count": len(part.node_ids), "bridge_refs": part.bridge_refs}
                for part in partitions
            ],
        },
        ensure_ascii=False,
    )


@tool()
def record_k8s_topology_findings(snapshot_id, subgraph_id, issues, config=None):
    finding = {"snapshot_id": snapshot_id, "subgraph_id": subgraph_id, "issues": issues}
    store_finding(snapshot_id, finding)
    return json.dumps({"status": "ok", "snapshot_id": snapshot_id, "subgraph_id": subgraph_id}, ensure_ascii=False)


@tool()
def list_k8s_topology_findings(snapshot_id, config=None):
    findings = get_findings(snapshot_id)
    return json.dumps({"snapshot_id": snapshot_id, "finding_count": len(findings), "findings": findings}, ensure_ascii=False)


@tool()
def get_k8s_topology_subgraph(snapshot_id, subgraph_id, max_evidence_tokens=1200, config=None):
    subgraph = _load_subgraph_payload(snapshot_id=snapshot_id, subgraph_id=subgraph_id)
    return json.dumps(
        {
            "snapshot_id": snapshot_id,
            "subgraph_id": subgraph_id,
            "summary": subgraph["summary"],
            "bridge_refs": subgraph["bridge_refs"],
            "evidence": subgraph["evidence"],
            "covered_resources": subgraph["covered_resources"],
            "remaining_budget": max(0, max_evidence_tokens - subgraph["estimated_tokens"]),
        },
        ensure_ascii=False,
    )


@tool()
def summarize_k8s_topology_findings(snapshot_id, config=None):
    findings = get_findings(snapshot_id)
    return json.dumps(
        {
            "snapshot_id": snapshot_id,
            "global_summary": {
                "problem_count": sum(len(item["issues"]) for item in findings),
                "bridge_ref_count": len({ref for item in findings for issue in item["issues"] for ref in issue.get("bridge_refs", [])}),
            },
            "findings": findings,
        },
        ensure_ascii=False,
    )
```

- [ ] **Step 5: Export the new tools only where the K8s topic needs them**

Update the restricted toolkit module rather than broadening unrelated toolkits:

```python
from apps.opspilot.metis.llm.tools.kubernetes.topology_tools import (
    build_k8s_topology_snapshot,
    get_k8s_topology_subgraph,
    list_k8s_topology_findings,
    record_k8s_topology_findings,
    summarize_k8s_topology_findings,
)

__all__ = [
    "verify_kubernetes_connection",
    "describe_kubernetes_resource",
    "normalize_alert_event",
    "resolve_k8s_target_from_alert",
    "build_k8s_topology_snapshot",
    "get_k8s_topology_subgraph",
    "record_k8s_topology_findings",
    "list_k8s_topology_findings",
    "summarize_k8s_topology_findings",
]
```

- [ ] **Step 6: Re-run topology and toolkit tests**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py apps/opspilot/tests/test_kubernetes_data_collection_tools.py -v
```

Expected: topology memory tests pass and toolkit metadata assertions can now be updated in the next task.

- [ ] **Step 7: Commit the tool layer**

```bash
git add server/apps/opspilot/metis/llm/tools/kubernetes/topology_memory.py server/apps/opspilot/metis/llm/tools/kubernetes/topology_tools.py server/apps/opspilot/metis/llm/tools/kubernetes/__init__.py server/apps/opspilot/metis/llm/tools/kubernetes_data_collection.py server/apps/opspilot/tests/test_kubernetes_topology_tools.py
git commit -m "feat: add k8s topology analysis tools"
```

### Task 5: Wire the built-in K8s topic prompt to graph-first agentic behavior

**Files:**
- Modify: `server/apps/opspilot/management/chatflow_data/k8s/check.txt`
- Modify: `server/apps/opspilot/management/chatflow_data/k8s/format.txt`
- Modify: `server/apps/opspilot/tests/test_kubernetes_data_collection_tools.py`
- Create: `server/apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py`

- [ ] **Step 1: Add failing prompt and agent-flow tests**

Capture the required guardrails before editing the prompts:

```python
def test_builtin_k8s_chatflow_prompt_requires_topology_first():
    from pathlib import Path

    chatflow_dir = Path(__file__).resolve().parents[1] / "management" / "chatflow_data" / "k8s"
    check_prompt = (chatflow_dir / "check.txt").read_text(encoding="utf-8")

    assert "build_k8s_topology_snapshot" in check_prompt
    assert "get_k8s_topology_subgraph" in check_prompt
    assert "record_k8s_topology_findings" in check_prompt
    assert "禁止直接遍历全集群 YAML" in check_prompt
```

And add a ReAct-style prompt behavior test:

```python
async def test_k8s_topology_prompt_prefers_graph_summary_before_raw_evidence():
    check_prompt = Path("apps/opspilot/management/chatflow_data/k8s/check.txt").read_text(encoding="utf-8")

    assert "先调用 build_k8s_topology_snapshot" in check_prompt
    assert "只有在子图范围内才允许读取证据" in check_prompt
```

- [ ] **Step 2: Run the prompt tests and verify they fail**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_data_collection_tools.py::test_builtin_k8s_chatflow_prompt_requires_topology_first -v
```

Expected: assertion failure because the current prompt is still the old quick-inspection flow.

- [ ] **Step 3: Rewrite `check.txt` to describe the graph-first execution order**

Replace the old direct inspection guidance with bounded tool choreography:

```text
你是 Kubernetes 运维专家，执行 K8s 工作集拓扑分析。

## 必须遵守的执行顺序
1. 先调用 build_k8s_topology_snapshot，获取 snapshot_id、规模统计和子图摘要。
2. 基于子图摘要决定优先分析哪些 subgraph_id。
3. 仅在单个子图范围内调用 get_k8s_topology_subgraph 读取证据。
4. 每分析完一个子图，立即调用 record_k8s_topology_findings 写入结构化发现。
5. 在完成局部分析后，调用 summarize_k8s_topology_findings 生成 topology_analysis_package。

## 硬约束
- 禁止直接遍历全集群 YAML。
- 禁止在没有 snapshot_id 的情况下开始明细分析。
- 必须优先看图摘要，再决定是否下钻原始证据。
- 如果子图返回 remaining_budget 偏低，先换下一个子图或收敛总结。
```

- [ ] **Step 4: Rewrite `format.txt` so the final answer consumes the synthesized package**

Keep the formatter from recollecting or asking the model to restitch raw evidence:

```text
你会收到 topology_analysis_package。

输出时：
- 先给出全局结论和高危问题
- 再说明共因与链式影响
- 再列出受影响工作负载与关键证据引用
- 最后给出修复建议

不要重新采集，不要假设不存在于 topology_analysis_package 的资源证据。
```

- [ ] **Step 5: Update toolkit metadata assertions**

Change the existing assertions to match the new restricted toolkit surface:

```python
assert "build_k8s_topology_snapshot" in tool_names
assert "get_k8s_topology_subgraph" in tool_names
assert "record_k8s_topology_findings" in tool_names
assert "summarize_k8s_topology_findings" in tool_names
assert "rollback_deployment" not in tool_names
```

- [ ] **Step 6: Run the prompt and toolkit tests**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_data_collection_tools.py apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py -v
```

Expected: the K8s topic now enforces graph-first prompt rules without changing the generic runtime.

- [ ] **Step 7: Commit the K8s-topic wiring**

```bash
git add server/apps/opspilot/management/chatflow_data/k8s/check.txt server/apps/opspilot/management/chatflow_data/k8s/format.txt server/apps/opspilot/tests/test_kubernetes_data_collection_tools.py server/apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py
git commit -m "feat: wire k8s topic to topology-first analysis"
```

### Task 6: Add real-cluster and budget regression coverage

**Files:**
- Modify: `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`
- Modify: `server/apps/opspilot/tests/test_k8s_scenario_e2e.py`

- [ ] **Step 1: Add a failing unit test for bounded subgraph evidence output**

Make sure the tool returns coverage metadata instead of unlimited evidence:

```python
def test_get_k8s_topology_subgraph_returns_remaining_budget_and_covered_resources(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.topology_tools import get_k8s_topology_subgraph

    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.topology_tools._load_subgraph_payload",
        return_value={
            "snapshot_id": "snap-1",
            "subgraph_id": "sg-1",
            "summary": {"node_count": 2},
            "evidence": {"deployments": [{"name": "api"}]},
            "bridge_refs": ["node:worker-a"],
        },
    )

    payload = json.loads(get_k8s_topology_subgraph.invoke({"snapshot_id": "snap-1", "subgraph_id": "sg-1", "max_evidence_tokens": 800}))

    assert payload["covered_resources"] == ["deployment:default/api"]
    assert payload["remaining_budget"] <= 800
```

- [ ] **Step 2: Run the bounded-evidence test and verify it fails**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py::test_get_k8s_topology_subgraph_returns_remaining_budget_and_covered_resources -v
```

Expected: assertion or missing implementation failure.

- [ ] **Step 3: Implement bounded subgraph evidence shaping**

Keep the tool payload explicit and small:

```python
@tool()
def get_k8s_topology_subgraph(snapshot_id, subgraph_id, max_evidence_tokens=1200, config=None):
    subgraph = _load_subgraph_payload(snapshot_id=snapshot_id, subgraph_id=subgraph_id)
    evidence = _trim_subgraph_evidence(subgraph["evidence"], max_evidence_tokens=max_evidence_tokens)
    return json.dumps(
        {
            "snapshot_id": snapshot_id,
            "subgraph_id": subgraph_id,
            "summary": subgraph["summary"],
            "bridge_refs": subgraph["bridge_refs"],
            "evidence": evidence["payload"],
            "covered_resources": evidence["covered_resources"],
            "remaining_budget": evidence["remaining_budget"],
        },
        ensure_ascii=False,
    )
```

- [ ] **Step 4: Extend the real-cluster scenario script with topology assertions**

Add one scenario that proves the topic can reason about shared relationships:

```python
def _assert_topology_analysis_package(pkg, scenario_name):
    assert pkg["snapshot"]["stats"]["deployment_count"] > 0, f"[{scenario_name}] deployment_count 应大于 0"
    assert pkg["global_summary"]["problem_count"] >= 1, f"[{scenario_name}] problem_count 应至少为 1"
    assert "shared_dependencies" in pkg["global_summary"], f"[{scenario_name}] 需要输出 shared_dependencies"


def run_topology_scenario():
    params = _build_invoke_params(
        llm_model=_get_gpt4o_model(),
        user_message="检查集群所有工作负载的配置，并重点识别共享 node、service、pvc、configmap 带来的链式风险",
        skill_tool_id=_get_skill_tool_id(),
    )
    raw_message = _invoke_chatflow(params)
    pkg = _extract_topology_package(raw_message)
    _assert_topology_analysis_package(pkg, "topology")
```

- [ ] **Step 5: Run the full K8s regression set**

Run:

```bash
cd server && uv run pytest apps/opspilot/tests/test_kubernetes_topology_tools.py apps/opspilot/tests/test_kubernetes_data_collection_tools.py apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py -v
```

And when a real cluster is available:

```bash
cd server && uv run python apps/opspilot/tests/test_k8s_scenario_e2e.py
```

Expected: unit tests pass in CI-style execution, and the real-cluster script emits a topology package that includes shared-dependency or bridge-style findings.

- [ ] **Step 6: Commit the regression coverage**

```bash
git add server/apps/opspilot/tests/test_kubernetes_topology_tools.py server/apps/opspilot/tests/test_k8s_scenario_e2e.py
git commit -m "test: cover k8s topology analysis flow"
```

### Task 7: Final verification and spec-to-plan readback

**Files:**
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_schema.py`
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_snapshot.py`
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_graph.py`
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_memory.py`
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes/topology_tools.py`
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes/__init__.py`
- Verify: `server/apps/opspilot/metis/llm/tools/kubernetes_data_collection.py`
- Verify: `server/apps/opspilot/management/chatflow_data/k8s/check.txt`
- Verify: `server/apps/opspilot/management/chatflow_data/k8s/format.txt`
- Verify: `server/apps/opspilot/tests/test_kubernetes_topology_tools.py`
- Verify: `server/apps/opspilot/tests/test_kubernetes_data_collection_tools.py`
- Verify: `server/apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py`
- Verify: `server/apps/opspilot/tests/test_k8s_scenario_e2e.py`

- [ ] **Step 1: Run the focused automated test suite**

Run:

```bash
cd server && uv run pytest \
  apps/opspilot/tests/test_kubernetes_topology_tools.py \
  apps/opspilot/tests/test_kubernetes_data_collection_tools.py \
  apps/opspilot/tests/react_agent/cases/test_k8s_topology_agent_flow.py -v
```

Expected: all focused topology and chatflow tests pass.

- [ ] **Step 2: Re-read the implementation against the design requirements**

Confirm each item is visibly satisfied in code:

```md
- K8s topic only; no generic agent runtime rewrite
- snapshot -> graph -> subgraph -> finding memory flow exists
- graph partitioning emits bridge_refs
- tools return remaining_budget and covered_resources
- prompts enforce graph-first, bounded-evidence behavior
- local findings persist outside chat history
- real-cluster script validates relationship-aware output
```

- [ ] **Step 3: Create the final handoff commit**

```bash
git add server/apps/opspilot/metis/llm/tools/kubernetes server/apps/opspilot/metis/llm/tools/kubernetes_data_collection.py server/apps/opspilot/management/chatflow_data/k8s server/apps/opspilot/tests
git commit -m "feat: add k8s agentic topology analysis pipeline"
```
