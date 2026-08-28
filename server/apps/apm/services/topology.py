from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from math import ceil

from apps.apm.adapters.span_aliases import (
    CLIENT_SPAN_KINDS,
    ENTRY_SPAN_KINDS,
    InferredDownstream,
    infer_downstream,
    is_user_request_entry,
)
from apps.apm.services.contracts import (
    SpanDetail,
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
    TopologySampleQuery,
    TopologySampleTrace,
    TopologyStore,
    TopologyTarget,
    TopologyTraceSample,
    TraceDetail,
)
from apps.apm.services.identity import normalize_identity

MAX_TOPOLOGY_WINDOW = timedelta(days=7)
MAX_TOPOLOGY_TARGETS = 30
MAX_TOPOLOGY_SAMPLE_TRACES = 200
MAX_SAMPLE_TRACES = 5
MAX_INFERRED_ATTR_VALUES = 5
ERROR_RATE_CRITICAL = 0.05
ERROR_RATE_WARNING = 0.01
INSTRUMENTED = "instrumented"
INFERRED = "inferred"
USER_REQUEST = "user_request"


def _identity(namespace: str, name: str, environment: str) -> tuple[str, str, str]:
    return normalize_identity(namespace), normalize_identity(name), environment


def _instrumented_node_id(identity: tuple[str, str, str]) -> str:
    return ":".join(identity)


def _inferred_node_id(fold_key: str, environment: str) -> str:
    return f"inferred:{environment}:{fold_key}"


def _user_request_node_id(environment: str) -> str:
    return f"user_request:{environment}"


def health_from_error_rate(error_rate: float | None) -> str:
    if error_rate is None:
        return "unknown"
    if error_rate >= ERROR_RATE_CRITICAL:
        return "critical"
    if error_rate >= ERROR_RATE_WARNING:
        return "warning"
    return "healthy"


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _error_rate(error_count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return error_count / total


def _span_matches_slice(
    span: SpanDetail,
    *,
    status: str | None,
    span_name: str | None,
    min_duration_ms: float | None,
    environment: str | None,
) -> bool:
    if environment is not None and span.environment != environment:
        return False
    if span_name is not None and span.name != span_name:
        return False
    if status is not None and span.status != status:
        return False
    if min_duration_ms is not None and span.duration_ms < min_duration_ms:
        return False
    return True


def _trace_matches_slice(
    detail: TraceDetail,
    *,
    status: str | None,
    span_name: str | None,
    min_duration_ms: float | None,
    environment: str | None,
) -> bool:
    if status == "ok" and any(span.status == "error" for span in detail.spans):
        return False
    return any(
        _span_matches_slice(
            span,
            status=status,
            span_name=span_name,
            min_duration_ms=min_duration_ms,
            environment=environment,
        )
        for span in detail.spans
    )


class _InferredNodeMeta:
    def __init__(self, fold_key: str, system: str, environment: str) -> None:
        self.fold_key = fold_key
        self.system = system
        self.environment = environment
        self.endpoints: list[str] = []
        self.db_names: list[str] = []

    def observe(self, inferred: InferredDownstream) -> None:
        endpoint = inferred.peer_address
        if endpoint and endpoint not in self.endpoints and len(self.endpoints) < MAX_INFERRED_ATTR_VALUES:
            self.endpoints.append(endpoint)
        if inferred.db_name and inferred.db_name not in self.db_names and len(self.db_names) < MAX_INFERRED_ATTR_VALUES:
            self.db_names.append(inferred.db_name)

    @property
    def peer_address(self) -> str:
        return ", ".join(self.endpoints)

    @property
    def db_name(self) -> str:
        return ", ".join(self.db_names)


class _MetricBucket:
    def __init__(self) -> None:
        self.durations: list[float] = []
        self.error_count = 0
        self.samples: list[TopologySampleTrace] = []

    def add(self, span: SpanDetail, *, trace_id: str, caller_service_name: str, inferred: InferredDownstream | None = None) -> None:
        self.durations.append(span.duration_ms)
        if span.status == "error":
            self.error_count += 1
        if any(item.trace_id == trace_id for item in self.samples):
            return
        if len(self.samples) >= MAX_SAMPLE_TRACES:
            return
        self.samples.append(
            TopologySampleTrace(
                trace_id=trace_id,
                span_id=span.span_id,
                span_name=span.name,
                started_at=span.started_at,
                duration_ms=span.duration_ms,
                status=span.status,
                caller_service_name=caller_service_name,
                peer_address=inferred.peer_address if inferred else "",
                db_name=inferred.db_name if inferred else "",
            )
        )

    @property
    def count(self) -> int:
        return len(self.durations)


class DjangoApmTopologyService:
    """从有界 Trace 样本聚合组织可见的服务调用图，并在样本上识别推断下游。"""

    def __init__(self, topology_store: TopologyStore, metric_store=None):
        self.topology_store = topology_store

    def build(
        self,
        targets: Sequence[TopologyTarget],
        *,
        started_at: datetime,
        ended_at: datetime,
        environment: str | None = None,
        status: str | None = None,
        span_name: str | None = None,
        min_duration_ms: float | None = None,
        include_inferred: bool = False,
        include_user_request: bool = False,
    ) -> TopologyGraph:
        if ended_at <= started_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > MAX_TOPOLOGY_WINDOW:
            raise ValueError("拓扑查询时间窗不能超过 7 天")
        if status is not None and status not in {"ok", "error"}:
            raise ValueError("status 仅支持 ok 或 error")
        if min_duration_ms is not None and min_duration_ms < 0:
            raise ValueError("min_duration_ms 不能为负数")

        unique_targets = list(dict.fromkeys(targets))
        truncated_targets = len(unique_targets) > MAX_TOPOLOGY_TARGETS
        selected_targets = unique_targets[:MAX_TOPOLOGY_TARGETS]
        visible: dict[tuple[str, str, str], TopologyTarget] = {}
        languages_by_identity: dict[tuple[str, str, str], str] = {}
        for target in selected_targets:
            identity = _identity(target.service_namespace, target.service_name, target.environment)
            visible[identity] = target
            languages_by_identity[identity] = target.language
        service_names = tuple(dict.fromkeys(target.service_name for target in selected_targets if target.service_name))

        sample = self._load_sample(
            TopologySampleQuery(
                started_at=started_at,
                ended_at=ended_at,
                service_names=service_names,
                environment=environment,
                status=status,
                span_name=span_name,
                min_duration_ms=min_duration_ms,
                limit=MAX_TOPOLOGY_SAMPLE_TRACES,
            )
        )
        traces = [
            detail
            for detail in sample.traces
            if detail.spans
            and _trace_matches_slice(
                detail,
                status=status,
                span_name=span_name,
                min_duration_ms=min_duration_ms,
                environment=environment,
            )
        ]

        window_seconds = max(1.0, (ended_at - started_at).total_seconds())
        node_metrics: dict[str, _MetricBucket] = defaultdict(_MetricBucket)
        edge_metrics: dict[tuple[str, str], _MetricBucket] = defaultdict(_MetricBucket)
        instrumented_nodes: dict[str, tuple[str, str, str]] = {}
        inferred_nodes: dict[str, _InferredNodeMeta] = {}
        user_request_nodes: dict[str, str] = {}
        contributing_traces = 0

        for detail in traces:
            contributed = self._ingest_trace(
                detail,
                visible=visible,
                include_inferred=include_inferred,
                include_user_request=include_user_request,
                node_metrics=node_metrics,
                edge_metrics=edge_metrics,
                instrumented_nodes=instrumented_nodes,
                inferred_nodes=inferred_nodes,
                user_request_nodes=user_request_nodes,
            )
            if contributed:
                contributing_traces += 1

        nodes = tuple(
            sorted(
                (
                    *(
                        self._instrumented_node(
                            node_id,
                            identity,
                            node_metrics[node_id],
                            language=languages_by_identity.get(identity, ""),
                            window_seconds=window_seconds,
                        )
                        for node_id, identity in instrumented_nodes.items()
                    ),
                    *(self._inferred_node(node_id, meta, node_metrics[node_id]) for node_id, meta in inferred_nodes.items()),
                    *(
                        self._user_request_node(node_id, environment, node_metrics[node_id])
                        for node_id, environment in user_request_nodes.items()
                    ),
                ),
                key=lambda node: (node.kind, node.service_name, node.id),
            )
        )
        edges = tuple(
            sorted(
                (self._edge(source, target, bucket) for (source, target), bucket in edge_metrics.items() if bucket.count),
                key=lambda edge: (edge.source, edge.target),
            )
        )
        diagnostics: list[str] = []
        if sample.omitted_trace_fetches:
            diagnostics.append(f"omitted_trace_fetches:{sample.omitted_trace_fetches}")
        truncated = truncated_targets or sample.truncated
        return TopologyGraph(
            nodes=nodes,
            edges=edges,
            sampled_traces=contributing_traces,
            truncated=truncated,
            data_state="available" if edges else "no_data",
            diagnostics=tuple(diagnostics),
        )

    def _load_sample(self, query: TopologySampleQuery) -> TopologyTraceSample:
        if not query.service_names:
            return TopologyTraceSample((), False)
        return self.topology_store.sample_traces(query)

    def _ingest_trace(
        self,
        detail: TraceDetail,
        *,
        visible: dict[tuple[str, str, str], TopologyTarget],
        include_inferred: bool,
        include_user_request: bool,
        node_metrics: dict[str, _MetricBucket],
        edge_metrics: dict[tuple[str, str], _MetricBucket],
        instrumented_nodes: dict[str, tuple[str, str, str]],
        inferred_nodes: dict[str, _InferredNodeMeta],
        user_request_nodes: dict[str, str],
    ) -> bool:
        spans_by_id = {span.span_id: span for span in detail.spans}
        children_by_parent: dict[str, list[SpanDetail]] = defaultdict(list)
        for span in detail.spans:
            if span.parent_span_id:
                children_by_parent[span.parent_span_id].append(span)
        contributed = False
        involved: set[tuple[str, str, str]] = set()

        for span in detail.spans:
            parent = spans_by_id.get(span.parent_span_id or "")
            if parent is None:
                continue
            parent_identity = _identity(parent.service_namespace, parent.service_name, parent.environment)
            child_identity = _identity(span.service_namespace, span.service_name, span.environment)
            if parent_identity == child_identity:
                continue
            if parent_identity not in visible or child_identity not in visible:
                continue
            source_id = _instrumented_node_id(parent_identity)
            target_id = _instrumented_node_id(child_identity)
            instrumented_nodes[source_id] = parent_identity
            instrumented_nodes[target_id] = child_identity
            involved.add(parent_identity)
            involved.add(child_identity)
            metric_span = parent if parent.kind in CLIENT_SPAN_KINDS else span
            edge_metrics[(source_id, target_id)].add(
                metric_span,
                trace_id=detail.trace_id,
                caller_service_name=parent.service_name,
            )
            contributed = True

        if include_inferred:
            for span in detail.spans:
                if span.kind not in CLIENT_SPAN_KINDS:
                    continue
                caller_identity = _identity(span.service_namespace, span.service_name, span.environment)
                if caller_identity not in visible:
                    continue
                if any(
                    normalize_identity(child.service_name) != normalize_identity(span.service_name)
                    for child in children_by_parent.get(span.span_id, ())
                ):
                    continue
                inferred = infer_downstream(span.attributes)
                if inferred is None:
                    continue
                source_id = _instrumented_node_id(caller_identity)
                target_id = _inferred_node_id(inferred.fold_key, caller_identity[2])
                instrumented_nodes[source_id] = caller_identity
                meta = inferred_nodes.get(target_id)
                if meta is None:
                    meta = _InferredNodeMeta(inferred.fold_key, inferred.system, caller_identity[2])
                    inferred_nodes[target_id] = meta
                meta.observe(inferred)
                involved.add(caller_identity)
                edge_metrics[(source_id, target_id)].add(
                    span,
                    trace_id=detail.trace_id,
                    caller_service_name=span.service_name,
                    inferred=inferred,
                )
                node_metrics[target_id].add(
                    span,
                    trace_id=detail.trace_id,
                    caller_service_name=span.service_name,
                    inferred=inferred,
                )
                contributed = True

        if include_user_request:
            for span in detail.spans:
                if span.parent_span_id and span.parent_span_id in spans_by_id:
                    continue
                if not is_user_request_entry(span.kind, span.attributes):
                    continue
                identity = _identity(span.service_namespace, span.service_name, span.environment)
                if identity not in visible:
                    continue
                source_id = _user_request_node_id(identity[2])
                target_id = _instrumented_node_id(identity)
                instrumented_nodes[target_id] = identity
                involved.add(identity)
                user_request_nodes[source_id] = identity[2]
                edge_metrics[(source_id, target_id)].add(span, trace_id=detail.trace_id, caller_service_name="")
                node_metrics[source_id].add(span, trace_id=detail.trace_id, caller_service_name="")
                contributed = True

        for span in detail.spans:
            identity = _identity(span.service_namespace, span.service_name, span.environment)
            if identity not in involved or identity not in visible:
                continue
            if span.kind not in ENTRY_SPAN_KINDS:
                continue
            node_id = _instrumented_node_id(identity)
            node_metrics[node_id].add(span, trace_id=detail.trace_id, caller_service_name=span.service_name)

        for identity in involved:
            node_id = _instrumented_node_id(identity)
            if node_metrics[node_id].count:
                continue
            fallback = next(
                (span for span in detail.spans if _identity(span.service_namespace, span.service_name, span.environment) == identity),
                None,
            )
            if fallback is not None:
                node_metrics[node_id].add(fallback, trace_id=detail.trace_id, caller_service_name=fallback.service_name)
        return contributed

    @staticmethod
    def _instrumented_node(
        node_id: str,
        identity: tuple[str, str, str],
        bucket: _MetricBucket,
        *,
        language: str,
        window_seconds: float,
    ) -> TopologyNode:
        error_rate = _error_rate(bucket.error_count, bucket.count)
        return TopologyNode(
            id=node_id,
            service_namespace=identity[0],
            service_name=identity[1],
            environment=identity[2],
            health=health_from_error_rate(error_rate),
            sampled_spans=bucket.count,
            error_spans=bucket.error_count,
            language=language,
            kind=INSTRUMENTED,
            request_rate=(bucket.count / window_seconds) if bucket.count else None,
            error_rate=error_rate,
            p95_ms=_percentile(bucket.durations, 0.95),
            sample_traces=tuple(bucket.samples),
        )

    @staticmethod
    def _inferred_node(
        node_id: str,
        meta: _InferredNodeMeta,
        bucket: _MetricBucket,
    ) -> TopologyNode:
        error_rate = _error_rate(bucket.error_count, bucket.count)
        return TopologyNode(
            id=node_id,
            service_namespace="",
            service_name=meta.fold_key,
            environment=meta.environment,
            health=health_from_error_rate(error_rate),
            sampled_spans=bucket.count,
            error_spans=bucket.error_count,
            language="",
            kind=INFERRED,
            fold_key=meta.fold_key,
            inferred_system=meta.system,
            peer_address=meta.peer_address,
            db_name=meta.db_name,
            request_rate=None,
            error_rate=error_rate,
            p95_ms=_percentile(bucket.durations, 0.95),
            sample_traces=tuple(bucket.samples),
        )

    @staticmethod
    def _user_request_node(node_id: str, environment: str, bucket: _MetricBucket) -> TopologyNode:
        """用户请求入口虚拟节点：不带 RED、健康度中性，指标只挂在出边上。"""

        return TopologyNode(
            id=node_id,
            service_namespace="",
            service_name=USER_REQUEST,
            environment=environment,
            health="unknown",
            sampled_spans=bucket.count,
            error_spans=0,
            language="",
            kind=USER_REQUEST,
            request_rate=None,
            error_rate=None,
            p95_ms=None,
            sample_traces=tuple(bucket.samples),
        )

    @staticmethod
    def _edge(source: str, target: str, bucket: _MetricBucket) -> TopologyEdge:
        error_rate = _error_rate(bucket.error_count, bucket.count)
        average = sum(bucket.durations) / bucket.count if bucket.count else 0.0
        return TopologyEdge(
            source=source,
            target=target,
            health=health_from_error_rate(error_rate),
            sampled_calls=bucket.count,
            error_calls=bucket.error_count,
            average_duration_ms=average,
            p95_ms=_percentile(bucket.durations, 0.95),
            error_rate=error_rate,
            sample_traces=tuple(bucket.samples),
        )
