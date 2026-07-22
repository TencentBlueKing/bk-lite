# Historical Superpowers change: 2026-06-01-opspilot-k8s-agentic-topology-analysis

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-01-opspilot-k8s-agentic-topology-analysis.md

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

## specs: 2026-06-01-opspilot-k8s-agentic-topology-analysis-design.md

## 背景

当前 OpsPilot 已经可以跑通 Kubernetes 配置检查的最小闭环：用户提问后，Agent 调用 Kubernetes 工具拿到工作负载与配置检查结果，再生成摘要报告。

现阶段的致命问题是，当集群工作负载数量增长后，主链路会把过多原始 YAML、检查结果和中间分析内容直接塞进同一轮上下文，导致 token 成本和上下文长度快速失控。与此同时，简单按 workload 切批又会破坏 workload 与 node、service、PVC、configmap 等对象之间的关系，导致最终报告只能看到局部问题，看不到全局因果链。

本专题需要在保持“AI 主导分析”的前提下，解决两类问题：

- **规模问题**：全集群检查时不能因工作负载数量增长而打爆主 Agent token。
- **全貌问题**：AI 必须能够洞察 workload 之间、workload 与 node 之间、以及 workload 与周边 K8s 资源之间的关系。

## 目标

- 保留“K8s 全量检查”语义，不退化成只看用户手动缩小后的对象范围。
- 保持 AI 主导：AI 负责决定下钻方向、关系归因、最终结论和修复建议。
- 通过关系图驱动的分层分析，避免主 Agent 上下文随全集群规模线性膨胀。
- 让最终报告能够识别共因、链式影响和跨 workload 的全局问题。
- 将能力收敛在 OpsPilot 的 K8s 工作集专题内，避免污染其他模块和其他智能体场景。
- 后续实现必须采用 TDD 护栏，并允许使用本地 K8s 环境做端到端验证。

## 非目标

- 不构建跨 CMDB、日志、告警、主机等多领域统一知识图平台。
- 不改造非 K8s 专题的通用执行链路。
- 不重做当前 UI、交互或前端展示层。
- 不把该专题退化成纯规则扫描器或纯代码驱动报告生成器。
- 不在第一版中扩展到 K8s 之外的专题能力。

## 现状

### 当前问题

- 主 Agent 会在一次执行中消费过多工作负载原始 YAML、配置检查结果与中间总结，token 预算不可控。
- 当对象数量较多时，现有最小闭环虽然能“跑完”，但无法保证稳定性与成本。
- 若简单按 workload 数量分批，service selector、共享 node、共享 PVC、共享 configmap/secret、ownerReferences 等关系会被切断，AI 难以看到全貌。

### 设计约束

- 这是 **OpsPilot K8s 工作集专题能力**，不能把专用的图构造、局部发现 schema、K8s prompt、K8s 中间存储抽象成全平台通用底座。
- Agent 会被勾选 K8s 工具集合，因此方案应是 **agentic** 的：Agent 借助提示词和工具自主决策，而不是被硬编码规则脚本完全驱动。
- 工具层需要提供预算感知和数据裁剪能力，避免 agentic 执行再次把主上下文打爆。

## 设计决策

### 1. 采用“关系图驱动的 Agentic Map-Reduce”

本专题的核心架构不是“把全集群结果一次交给一个 Agent”，也不是“按固定数量分页后盲目分批”，而是：

1. 先构建 Kubernetes 资源快照与显式关系图。
2. 再按关系子图切分分析单元。
3. 每个分析单元由 AI 读取“子图摘要 + 子图相关原始证据”，输出结构化局部发现。
4. 最后由全局汇总 AI 基于所有局部发现和全局拓扑摘要生成最终报告。

这样既保留 AI 对原始证据的直读能力，又把 token 风险拆散到多个可控批次。

### 2. 关系图是 AI 的观察面，不是替代 AI 的规则引擎

代码侧负责构建显式关系图，主要用于：

- 保留对象之间的真实拓扑关系
- 为 agent 提供“先看哪里、该扩展哪一侧”的决策基础
- 按关系连通性切分子图，而不是按对象数量硬切

代码侧不负责生成最终问题结论，不用规则直接替代 AI 的风险归因和修复建议。

### 3. 决策权交给 Agent，预算护栏交给工具

为了保持 agentic 设计，专题内会提供一组 K8s 工具，让 Agent 自主决定：

- 是否先建全局图
- 先分析哪些子图
- 哪些桥接关系需要继续追踪
- 哪些对象需要展开原始 YAML 或检查详情

但工具必须带有强护栏：

- 图摘要工具返回结构化拓扑摘要，而不是整图全文
- 资源详情工具支持按对象、按字段、按分页、按片段返回
- 子图读取工具具备 token 预算约束
- 中间发现写入外部结构化存储，避免只能依赖会话上下文

### 4. 能力必须收敛在 K8s 专题域

本方案新增的是 **K8s 专题执行引擎**，不是全局 Agent 框架重构。它只复用现有 Agent 宿主和对话入口，不向其他专题暴露通用关系图平台、通用分析中间层或通用 prompt 契约。

## 总体架构

### 1. Snapshot Builder

负责收集一次场景执行所需的 Kubernetes 快照，至少包括：

- workload（Deployment、StatefulSet、DaemonSet、Job、CronJob）
- Pod、Node
- Service、Ingress
- PVC / PV
- ConfigMap / Secret 挂载关系
- HPA / PDB
- 事件与现有配置检查结果

该层输出带版本号的快照，后续所有子图分析共享同一份快照，避免不同批次读取到不一致状态。

### 2. Graph Builder

将快照转成显式关系图。建议保留以下边类型：

- workload -> pod
- pod -> node
- ownerReferences
- service -> selected workload/pod
- ingress -> backend service
- workload -> pvc/pv
- workload -> configmap/secret
- hpa/pdb -> workload
- namespace 内关键依赖
- 跨 namespace 的显式调用或引用关系（仅限 K8s 专题已能确认的关系）

### 3. Subgraph Partitioner

根据“关系连通性 + token 预算”切分子图。切分目标不是绝对均匀，而是：

- 尽量让强关联对象留在同一子图
- 当证据体积逼近预算阈值时再截断
- 为跨子图关系生成 `bridge_refs`
- 保留每个子图的摘要、边界和桥接信息

### 4. Local AI Analyzer

每个子图由一个局部 AI 分析单元处理。输入包括：

- 子图结构化摘要
- 子图涉及的原始 YAML 或检查证据
- 明确的输出 schema
- 当前预算与已覆盖资源信息

输出必须是结构化局部发现，而不是长篇自由文本，例如：

- `issue_id`
- `severity`
- `impacted_resources`
- `evidence_refs`
- `suspected_root_causes`
- `fix_suggestions`
- `bridge_refs`
- `confidence`
- `next_suggested_queries`

### 5. Global Synthesizer

全局汇总层只消费：

- 全局图摘要
- 全部局部发现
- 需要补链的桥接关系

它负责：

- 去重与归并重复问题
- 识别跨子图共因
- 拼接链式影响
- 生成最终的自然语言专题报告
- 标注不确定性和冲突证据

## Agentic 执行机制

### Planner Agent

Planner Agent 是专题入口调度者。它根据用户问题决定：

- 是否先构建全量图
- 是否先限定某个 namespace、资源种类或高风险区域
- 是否需要继续拉取更多拓扑信息
- 是否需要对子图做再次拆分

Planner Agent 不直接吞全部原始 YAML，而是优先调用图摘要与统计类工具，再决定是否下钻。

### Local Analysis Agents

局部分析由一个或多个子 Agent 完成。它们共享同一套 K8s 专题提示词和输出 schema，但每次只看一个子图范围内的数据。

子 Agent 必须遵守以下约束：

- 优先利用关系图理解上下文，再读取原始 YAML
- 输出结构化局部发现
- 显式给出证据引用
- 发现桥接关系时返回进一步追踪建议

### Synthesizer Agent

最终汇总 Agent 不回看全集群原始数据，只消费局部发现和必要的桥接上下文。这样主 Agent 的上下文压力被限制在“摘要与发现层”，不会随全集群规模线性增长。

## 数据流

1. 用户在 OpsPilot 中触发 K8s 配置检查或场景执行。
2. 进入 K8s 专题 Orchestrator。
3. Orchestrator 调用 Snapshot Builder 采集资源快照。
4. Graph Builder 构建显式关系图并输出图摘要。
5. Planner Agent 基于问题和图摘要决定分析策略。
6. Subgraph Partitioner 生成一个或多个关系子图。
7. Local Analysis Agents 分别处理子图，输出局部发现并写入外部结构化存储。
8. Synthesizer Agent 拉取全部局部发现和全局拓扑摘要，生成最终报告。
9. 对话层只接收最终专题结果，不暴露专题内部中间产物。

## 隔离边界

### 入口隔离

- 仅在 K8s 工作集专题能力内接入。
- 不改变其他智能体场景默认执行方式。

### 存储隔离

- 快照、关系图、局部发现使用专属命名空间、表或缓存键前缀。
- 不与其他专题共享内部中间结果存储契约。

### Prompt 隔离

- Local Analyzer 和 Synthesizer 使用 K8s 专题专属提示词。
- 不把 K8s 关系图推理 prompt 迁移到全局基础 prompt。

### Schema 隔离

- 局部发现 schema、桥接引用、图摘要协议都视为 K8s 专题内部契约。
- 不抽象成跨模块统一问题图谱平台。

## Token 控制与外部记忆

### Token 控制原则

- 不依赖“在 prompt 中提醒模型少说一点”这种软约束。
- 预算必须由工具协议显式控制。

### 工具层预算能力

- 图工具返回 topology summary、统计信息、桥接关系，不返回无边界全文。
- 原始 YAML 工具支持按资源、按字段、按分页、按片段读取。
- 子图分析工具必须感知预算上限和已覆盖范围。
- Agent 每轮读取到 `remaining_budget` 和 `covered_resources`，避免重复拉取同一批证据。

### 外部记忆模型

局部发现必须落到结构化外部记忆中，至少包含：

- `snapshot_id`
- `subgraph_id`
- `resources`
- `issues`
- `evidence_refs`
- `bridge_refs`
- `confidence`
- `next_suggested_queries`

这样即便主对话上下文被裁剪，专题链路仍可断点续跑，不需要重新把所有局部结果塞回会话历史。

## 错误处理

- **子图过大**：自动继续拆分，不允许把超预算子图直接喂给模型。
- **桥接关系过多**：在全局汇总层标注为高耦合区域，并触发二次深挖。
- **局部发现冲突**：Synthesizer 必须显式保留冲突证据与不确定性，不得静默覆盖。
- **工具调用失败**：专题执行链路显式失败并返回可诊断信息，不吞错、不伪造成功。
- **执行中断**：已生成的局部发现可复用，支持断点续跑。

## 测试与验证

### TDD 护栏

本专题后续实现必须遵循 TDD：

1. 先写失败测试定义期望行为。
2. 再实现最小代码让测试通过。
3. 最后重构并继续收紧预算和边界。

TDD 在这里不仅用于保证代码正确，还用于防止实现阶段退化为：

- 纯规则流水线
- 无图的简单分页
- 再次把大量原始 YAML 回灌到主上下文

### 测试分层

- **单元测试**：图构造、边生成、子图切分、bridge refs、预算裁剪。
- **场景测试**：给定 K8s 资源快照，验证 Agent 是否先建图再下钻，并能基于桥接关系扩展分析。
- **端到端测试**：在本地 K8s 环境中执行真实专题链路，验证规模控制、关系洞察、失败恢复和最终报告质量。

### 本地 K8s 验证场景

本地 K8s 环境至少覆盖以下样例：

- 多个 workload 共享 node
- service selector 误配影响多个 workload
- 共用 PVC / ConfigMap / Secret 引发批量问题
- ownerReferences 或关联对象导致链式影响
- workload 数量逐步上升后，主 Agent 上下文仍保持稳定

### 验证标准

- 主 Agent 的上下文大小不再随全集群规模线性膨胀。
- Agent 能先构建图，再决定下钻和补链。
- 最终报告能识别全局共因和跨 workload 影响，而不只是罗列单点异常。
- 新能力只影响 K8s 专题，不影响其他模块。

## 风险与控制

### 风险

- 图构造不完整会导致关系丢失，最终分析仍然碎片化。
- 子图切分策略过粗会丢上下文，过细则会重新引发 token 爆炸。
- Agent 如果缺少预算护栏，可能重复读取同类证据，造成成本失控。
- 若过度抽象专题中间协议，容易污染其他专题和模块。

### 控制措施

- 第一版只覆盖 K8s 专题所需的关键关系边，不做全平台统一图谱抽象。
- 子图切分使用连通性与预算双约束，而不是单一对象数量阈值。
- 所有大对象读取工具都支持分页、字段裁剪和预算感知。
- 用 TDD 和本地 K8s 端到端样例锁住 agentic 行为与预算边界。

## 预期结果

完成后，OpsPilot 的 K8s 工作集专题将从“单轮上下文堆料式分析”升级为“关系图驱动的 agentic 分层分析”：

- AI 仍然是分析主体，而不是被规则引擎替代；
- token 风险被拆解到多个可控分析单元；
- 最终报告能看到 workload、node 与周边资源之间的全局关系；
- 该能力保持在 K8s 专题内聚演进，不污染其他模块。
