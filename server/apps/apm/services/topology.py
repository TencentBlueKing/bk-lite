from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from apps.apm.services.contracts import (
    ServiceDependency,
    TopologyDependencyQuery,
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
    TopologyStore,
    TopologyTarget,
)
from apps.apm.services.identity import normalize_identity


MAX_TOPOLOGY_WINDOW = timedelta(days=7)
MAX_TOPOLOGY_TARGETS = 30


def _identity(namespace: str, name: str, environment: str) -> tuple[str, str, str]:
    return normalize_identity(namespace), normalize_identity(name), environment


def _node_id(identity: tuple[str, str, str]) -> str:
    return ":".join(identity)


class DjangoApmTopologyService:
    """从 VT servicegraph 依赖聚合构建组织可见的服务调用图。"""

    def __init__(self, topology_store: TopologyStore):
        self.topology_store = topology_store

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
        identities_by_name: dict[str, list[tuple[str, str, str]]] = {}
        for target in selected_targets:
            identity = _identity(target.service_namespace, target.service_name, target.environment)
            identities_by_name.setdefault(identity[1], []).append(identity)

        dependencies = self.topology_store.service_dependencies(
            TopologyDependencyQuery(started_at=started_at, ended_at=ended_at)
        )
        visible_dependencies: list[tuple[ServiceDependency, tuple[str, str, str], tuple[str, str, str]]] = []
        ambiguous = 0
        for dependency in dependencies:
            parents = identities_by_name.get(normalize_identity(dependency.parent_service_name), [])
            children = identities_by_name.get(normalize_identity(dependency.child_service_name), [])
            if len(parents) != 1 or len(children) != 1:
                ambiguous += 1
                continue
            if parents[0] == children[0]:
                continue
            visible_dependencies.append((dependency, parents[0], children[0]))

        node_calls: dict[tuple[str, str, str], int] = {}
        for dependency, source, target in visible_dependencies:
            node_calls[source] = node_calls.get(source, 0) + dependency.call_count
            node_calls[target] = node_calls.get(target, 0) + dependency.call_count

        nodes = tuple(
            TopologyNode(
                id=_node_id(identity),
                service_namespace=identity[0],
                service_name=identity[1],
                environment=identity[2],
                health="unknown",
                sampled_spans=calls,
                error_spans=0,
            )
            for identity, calls in sorted(node_calls.items())
        )
        edges = tuple(
            TopologyEdge(
                source=_node_id(source),
                target=_node_id(target),
                health="unknown",
                sampled_calls=dependency.call_count,
                error_calls=0,
                average_duration_ms=0,
            )
            for dependency, source, target in sorted(
                visible_dependencies,
                key=lambda item: (item[1], item[2]),
            )
        )
        sampled_calls = sum(dependency.call_count for dependency, _, _ in visible_dependencies)
        return TopologyGraph(
            nodes=nodes,
            edges=edges,
            sampled_traces=sampled_calls,
            truncated=truncated or ambiguous > 0,
            data_state="available" if visible_dependencies else "no_data",
            diagnostics=(f"omitted_ambiguous_dependencies:{ambiguous}",) if ambiguous else (),
        )
