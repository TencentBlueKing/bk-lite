'use client';

import Link from 'next/link';
import { Button, Empty, Tag, Typography } from 'antd';
import { formatDateTime, formatLatency, formatNumber, formatRequestRate } from '@/app/apm/components/metric-format';
import type { ApmTopologyEdge, ApmTopologyNode, ApmTopologySampleTrace, ApmTraceSummary } from '@/app/apm/types';
import type { TopologyCanvasSelection } from '@/app/apm/services/topology/topology-canvas';
import { isInferredTopologyNode } from '@/app/apm/services/topology/topology-layout';
import { useTranslation } from '@/utils/i18n';

export function topologyExploreHref(
  node: ApmTopologyNode,
  startedAt: string,
  endedAt: string,
  slice?: { status?: 'ok' | 'error'; span_name?: string; min_duration_ms?: number },
) {
  const params = new URLSearchParams({
    service_namespace: node.service_namespace,
    service_name: node.service_name,
    environment: node.environment,
    started_at: startedAt,
    ended_at: endedAt,
  });
  if (slice?.status) params.set('status', slice.status);
  if (slice?.span_name) params.set('span_name', slice.span_name);
  if (slice?.min_duration_ms != null) params.set('min_duration_ms', String(slice.min_duration_ms));
  return `/apm/explore/traces?${params.toString()}`;
}

export default function TopologyInspectPanel({
  nodes,
  edges,
  selection,
  traces,
  tracesLoading,
  startedAt,
  endedAt,
  serviceIds,
  isolated,
  slice,
  onSelectNode,
  onIsolate,
  onShowFullMap,
}: {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  selection: TopologyCanvasSelection | null;
  traces: ApmTraceSummary[];
  tracesLoading: boolean;
  startedAt: string;
  endedAt: string;
  serviceIds: Map<string, string>;
  isolated: boolean;
  slice?: { status?: 'ok' | 'error'; span_name?: string; min_duration_ms?: number };
  onSelectNode: (nodeId: string) => void;
  onIsolate: (nodeId: string) => void;
  onShowFullMap: () => void;
}) {
  const { t } = useTranslation();
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const selectedNode = selection?.kind === 'node' ? nodeMap.get(selection.id) : undefined;
  const selectedEdge = selection?.kind === 'edge' ? edges.find((edge) => edge.source === selection.source && edge.target === selection.target) : undefined;
  const source = selectedEdge ? nodeMap.get(selectedEdge.source) : undefined;
  const target = selectedEdge ? nodeMap.get(selectedEdge.target) : undefined;
  const inferred = isInferredTopologyNode(selectedNode) || isInferredTopologyNode(target);
  const incoming = selectedNode
    ? edges.filter((edge) => edge.target === selectedNode.id).flatMap((edge) => {
      const node = nodeMap.get(edge.source);
      return node ? [{ node, edge }] : [];
    })
    : [];
  const outgoing = selectedNode
    ? edges.filter((edge) => edge.source === selectedNode.id).flatMap((edge) => {
      const node = nodeMap.get(edge.target);
      return node ? [{ node, edge }] : [];
    })
    : [];
  const serviceHref = (node: ApmTopologyNode) => {
    if (isInferredTopologyNode(node)) return null;
    const serviceId = serviceIds.get(`${node.service_namespace}::${node.service_name}`);
    if (!serviceId) return null;
    const query = node.environment ? `?environment=${encodeURIComponent(node.environment)}` : '';
    return `/apm/services/${serviceId}${query}`;
  };
  const exploreNode = selectedNode && !isInferredTopologyNode(selectedNode)
    ? selectedNode
    : source && !isInferredTopologyNode(source)
      ? source
      : undefined;
  const sampleTraces: Array<ApmTopologySampleTrace | ApmTraceSummary> = selectedNode?.sample_traces?.length
    ? selectedNode.sample_traces
    : selectedEdge?.sample_traces?.length
      ? selectedEdge.sample_traces
      : traces;
  const sampleTitle = inferred
    ? t('apm.topology.sampleClientSpans', '样本 Client Span')
    : t('apm.topology.sampleTraces', '样本 Trace');

  const title = selectedNode
    ? selectedNode.service_name
    : selectedEdge && source && target
      ? t('apm.topology.edgeName', '{source} → {target}', { source: source.service_name, target: target.service_name })
      : t('apm.topology.overview', '总览');

  return (
    <aside aria-label={t('apm.topology.inspectPanel', '拓扑调查栏')} className="flex h-[640px] w-[320px] shrink-0 flex-col border-l border-[var(--color-border)] bg-[var(--color-bg)]">
      <div className="flex items-start justify-between gap-2 border-b border-[var(--color-border)] px-4 py-3">
        <div className="min-w-0">
          <Typography.Text type="secondary" className="!text-xs">{t('apm.topology.inspect', '调查')}</Typography.Text>
          <div className="flex items-center gap-2">
            <Typography.Title level={5} className="!mb-0 truncate" title={title}>{title}</Typography.Title>
            {isInferredTopologyNode(selectedNode) ? <Tag bordered={false}>{t('apm.topology.inferredBadge', '推断')}</Tag> : null}
          </div>
        </div>
        {isolated ? (
          <Button size="small" onClick={onShowFullMap}>{t('apm.topology.showFullMap', '显示全图')}</Button>
        ) : null}
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        {!selectedNode && !selectedEdge ? (
          <OverviewList nodes={nodes} onSelectNode={onSelectNode} />
        ) : null}
        {selectedNode ? (
          <>
            <dl className="grid grid-cols-1 gap-2 text-sm">
              <MetricRow label={t('apm.topology.errorCount', '错误数')} value={formatNumber(selectedNode.error_spans)} />
              <MetricRow label={t('apm.topology.totalCount', '总数')} value={formatNumber(selectedNode.sampled_spans)} />
              <MetricRow label={t('apm.common.p95', 'P95')} value={formatLatency(selectedNode.p95_ms ?? null, false, t)} />
              {isInferredTopologyNode(selectedNode) ? null : (
                <MetricRow label={t('apm.common.throughput', '吞吐量')} value={formatRequestRate(selectedNode.request_rate ?? null, false, t)} />
              )}
              {isInferredTopologyNode(selectedNode) && selectedNode.peer_address ? (
                <MetricRow label={t('apm.topology.peerAddress', '地址')} value={selectedNode.peer_address} />
              ) : null}
              {isInferredTopologyNode(selectedNode) && selectedNode.db_name ? (
                <MetricRow label={t('apm.topology.dbName', '库名')} value={selectedNode.db_name} />
              ) : null}
              {isInferredTopologyNode(selectedNode) && (selectedNode.peer_address || selectedNode.db_name) ? null : (
                <MetricRow label={t('apm.common.environment', '环境')} value={selectedNode.environment || t('apm.common.unset', '未设置')} />
              )}
            </dl>
            <div className="flex flex-wrap gap-2">
              <Button size="small" onClick={() => onIsolate(selectedNode.id)}>{t('apm.topology.isolate', '隔离一跳')}</Button>
              {serviceHref(selectedNode) ? (
                <Link href={serviceHref(selectedNode)!}>
                  <Button size="small">{t('apm.topology.openService', '服务详情')}</Button>
                </Link>
              ) : null}
              {exploreNode ? (
                <Link href={topologyExploreHref(exploreNode, startedAt, endedAt, slice)}>
                  <Button size="small">{t('apm.topology.seeMoreTraces', '更多调用链')}</Button>
                </Link>
              ) : null}
            </div>
            <NeighborList
              title={isInferredTopologyNode(selectedNode) ? t('apm.topology.caller', '调用方') : t('apm.topology.incoming', '入向服务')}
              items={incoming}
              onSelectNode={onSelectNode}
            />
            {isInferredTopologyNode(selectedNode) ? null : (
              <NeighborList
                title={t('apm.topology.outgoing', '出向服务')}
                items={outgoing}
                onSelectNode={onSelectNode}
              />
            )}
          </>
        ) : null}
        {selectedEdge && source && target ? (
          <>
            <dl className="grid grid-cols-1 gap-2 text-sm">
              <MetricRow label={t('apm.topology.errorCount', '错误数')} value={formatNumber(selectedEdge.error_calls)} />
              <MetricRow label={t('apm.topology.totalCount', '总数')} value={formatNumber(selectedEdge.sampled_calls)} />
              <MetricRow label={t('apm.common.p95', 'P95')} value={formatLatency(selectedEdge.p95_ms ?? null, false, t)} />
            </dl>
            {exploreNode ? (
              <Link href={topologyExploreHref(exploreNode, startedAt, endedAt, slice)}>
                <Button size="small">{t('apm.topology.seeMoreTraces', '更多调用链')}</Button>
              </Link>
            ) : null}
          </>
        ) : null}
        {selectedNode || selectedEdge ? (
          <section>
            <Typography.Text strong>{sampleTitle}</Typography.Text>
            {tracesLoading ? (
              <Typography.Text type="secondary" className="mt-2 block !text-xs">{t('apm.catalog.loading', '加载 APM 数据')}</Typography.Text>
            ) : sampleTraces.length ? (
              <ul className="mt-2 flex flex-col gap-2">
                {sampleTraces.map((trace) => {
                  const spanId = 'span_id' in trace ? trace.span_id : undefined;
                  const href = spanId
                    ? `/apm/explore/traces/${trace.trace_id}?span_id=${encodeURIComponent(spanId)}`
                    : `/apm/explore/traces/${trace.trace_id}`;
                  const label = 'span_name' in trace && trace.span_name
                    ? trace.span_name
                    : 'root_span_name' in trace
                      ? (trace.root_span_name || trace.trace_id)
                      : trace.trace_id;
                  const samplePeer = [
                    'peer_address' in trace ? trace.peer_address : '',
                    'db_name' in trace ? trace.db_name : '',
                  ].filter(Boolean).join(' · ');
                  return (
                    <li key={`${trace.trace_id}:${spanId || ''}`}>
                      <Link
                        className="block rounded-md border border-[var(--color-border)] px-2 py-1.5 hover:border-[var(--color-primary)]"
                        href={href}
                      >
                        <span className="block truncate text-sm">{label}</span>
                        <span className="text-xs text-[var(--color-text-3)]">
                          {formatLatency(trace.duration_ms, false, t)} · {formatDateTime(trace.started_at, false)}
                          {samplePeer ? ` · ${samplePeer}` : ''}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Empty className="!mt-3" image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('apm.topology.noSampleTraces', '当前选择没有样本 Trace')} />
            )}
          </section>
        ) : null}
      </div>
    </aside>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[var(--color-text-3)]">{label}</dt>
      <dd className="m-0 tabular-nums text-[var(--color-text-1)]">{value}</dd>
    </div>
  );
}

function OverviewList({ nodes, onSelectNode }: { nodes: ApmTopologyNode[]; onSelectNode: (nodeId: string) => void }) {
  const { t } = useTranslation();
  const sorted = [...nodes].sort((left, right) => left.service_name.localeCompare(right.service_name));
  if (!sorted.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('apm.topology.empty', '当前范围内没有观测到可用于构建拓扑的调用链。')} />;
  }
  return (
    <ul className="flex flex-col gap-1">
      {sorted.map((node) => (
        <li key={node.id}>
          <button
            type="button"
            className="flex w-full items-baseline justify-between gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[var(--color-fill-1)]"
            onClick={() => onSelectNode(node.id)}
          >
            <span className="truncate text-sm">
              {node.service_name}
              {isInferredTopologyNode(node) ? ` · ${t('apm.topology.inferredBadge', '推断')}` : ''}
            </span>
            <span className="shrink-0 tabular-nums text-xs text-[var(--color-text-3)]">
              {node.p95_ms == null ? t('apm.common.noData', '无数据') : formatLatency(node.p95_ms, false, t)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function NeighborList({
  title,
  items,
  onSelectNode,
}: {
  title: string;
  items: Array<{ node: ApmTopologyNode; edge: ApmTopologyEdge }>;
  onSelectNode: (nodeId: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <section>
      <Typography.Text strong>{title}</Typography.Text>
      {items.length ? (
        <ul className="mt-2 flex flex-col gap-1">
          {items.map(({ node, edge }) => (
            <li key={`${edge.source}-${edge.target}`}>
              <button
                type="button"
                className="flex w-full items-baseline justify-between gap-2 rounded-md px-2 py-1 text-left hover:bg-[var(--color-fill-1)]"
                onClick={() => onSelectNode(node.id)}
              >
                <span className="truncate text-sm">
                  {node.service_name}
                  {isInferredTopologyNode(node) ? ` · ${t('apm.topology.inferredBadge', '推断')}` : ''}
                </span>
                <span className="shrink-0 tabular-nums text-xs text-[var(--color-text-3)]">
                  {t('apm.topology.callCount', '{count} 次', { count: formatNumber(edge.sampled_calls) })}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <Typography.Text type="secondary" className="mt-2 block !text-xs">{t('apm.topology.none', '无')}</Typography.Text>
      )}
    </section>
  );
}
