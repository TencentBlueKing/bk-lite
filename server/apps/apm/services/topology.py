from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from apps.apm.services.contracts import (
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
    TopologyTarget,
    TraceSearchQuery,
    TraceStore,
)
from apps.apm.services.identity import normalize_identity


MAX_TOPOLOGY_WINDOW = timedelta(days=7)
MAX_TOPOLOGY_TARGETS = 30
TRACES_PER_TARGET = 10


def _identity(namespace: str, name: str, environment: str) -> tuple[str, str, str]:
    return normalize_identity(namespace), normalize_identity(name), environment


def _node_id(identity: tuple[str, str, str]) -> str:
    return ":".join(identity)


def _health(errors: int, total: int) -> str:
    if total <= 0:
        return "unknown"
    ratio = errors / total
    if ratio >= 0.1:
        return "critical"
    if errors:
        return "warning"
    return "healthy"


class DjangoApmTopologyService:
    """从有界 Trace 样本构建组织可见的服务调用图。"""

    def __init__(self, trace_store: TraceStore):
        self.trace_store = trace_store

    def build(
        self,
        targets: Sequence[TopologyTarget],
        *,
        started_at: datetime,
        ended_at: datetime,
    ) -> TopologyGraph:
        if ended_at <= started_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > MAX_TOPOLOGY_WINDOW:
            raise ValueError("拓扑查询时间窗不能超过 7 天")

        unique_targets = list(dict.fromkeys(targets))
        truncated = len(unique_targets) > MAX_TOPOLOGY_TARGETS
        selected_targets = unique_targets[:MAX_TOPOLOGY_TARGETS]
        allowed = {
            _identity(target.service_namespace, target.service_name, target.environment)
            for target in selected_targets
        }
        trace_ids: set[str] = set()
        for target in selected_targets:
            page = self.trace_store.search(
                TraceSearchQuery(
                    started_at=started_at,
                    ended_at=ended_at,
                    service_namespace=target.service_namespace,
                    service_name=target.service_name,
                    environment=target.environment,
                    limit=TRACES_PER_TARGET,
                )
            )
            trace_ids.update(item.trace_id for item in page.items)
            truncated = truncated or page.next_cursor is not None

        node_counts: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
        edge_counts: dict[tuple[tuple[str, str, str], tuple[str, str, str]], list[float]] = defaultdict(
            lambda: [0, 0, 0.0]
        )
        sampled_traces = 0
        for trace_id in sorted(trace_ids):
            detail = self.trace_store.get_trace(trace_id)
            if detail is None:
                continue
            sampled_traces += 1
            spans = {span.span_id: span for span in detail.spans}
            for span in detail.spans:
                current = _identity(span.service_namespace, span.service_name, span.environment)
                if current not in allowed:
                    continue
                node_counts[current][0] += 1
                node_counts[current][1] += int(span.status == "error")
                parent = spans.get(span.parent_span_id or "")
                if parent is None:
                    continue
                parent_identity = _identity(parent.service_namespace, parent.service_name, parent.environment)
                if parent_identity not in allowed or parent_identity == current:
                    continue
                edge = edge_counts[(parent_identity, current)]
                edge[0] += 1
                edge[1] += int(span.status == "error")
                edge[2] += max(0.0, span.duration_ms)

        nodes = tuple(
            TopologyNode(
                id=_node_id(identity),
                service_namespace=identity[0],
                service_name=identity[1],
                environment=identity[2],
                health=_health(counts[1], counts[0]),
                sampled_spans=counts[0],
                error_spans=counts[1],
            )
            for identity, counts in sorted(node_counts.items())
        )
        edges = tuple(
            TopologyEdge(
                source=_node_id(source),
                target=_node_id(target),
                health=_health(int(counts[1]), int(counts[0])),
                sampled_calls=int(counts[0]),
                error_calls=int(counts[1]),
                average_duration_ms=counts[2] / counts[0],
            )
            for (source, target), counts in sorted(edge_counts.items())
        )
        return TopologyGraph(
            nodes=nodes,
            edges=edges,
            sampled_traces=sampled_traces,
            truncated=truncated,
            data_state="available" if sampled_traces else "no_data",
        )
