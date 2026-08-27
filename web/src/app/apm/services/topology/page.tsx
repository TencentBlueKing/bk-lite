'use client';

import { ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { Alert, Button, Input, InputNumber, Segmented, Select } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import TopologyCanvas, {
  TopologyLegendDot,
  topologyHealthColors,
  type TopologyCanvasSelection,
  type TopologyLayoutMode,
} from '@/app/apm/services/topology/topology-canvas';
import TopologyInspectPanel from '@/app/apm/services/topology/topology-inspect-panel';
import { filterTopologyByKeyword, isolateTopologyNeighborhood } from '@/app/apm/services/topology/topology-layout';
import type { ApmTopologyGraph, ApmTraceSummary } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

export { default as TopologyCanvas } from '@/app/apm/services/topology/topology-canvas';

type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';
type PageState = CatalogStateKind | 'ready';
type RequestStatus = 'all' | 'ok' | 'error';

const windowMs: Record<TimeWindow, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

export default function ApmTopologyPage() {
  const { t } = useTranslation();
  const { getServices, getTopology, getTraces } = useApmApi();
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [state, setState] = useState<PageState>('loading');
  const [layout, setLayout] = useState<TopologyLayoutMode>('layered');
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('1h');
  const [environment, setEnvironment] = useState<string>();
  const [environmentOptions, setEnvironmentOptions] = useState<{ value: string; label: string }[]>([]);
  const [serviceIds, setServiceIds] = useState<Map<string, string>>(new Map());
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [requestStatus, setRequestStatus] = useState<RequestStatus>('all');
  const [spanName, setSpanName] = useState('');
  const [minDurationMs, setMinDurationMs] = useState<number | null>(null);
  const [selection, setSelection] = useState<TopologyCanvasSelection | null>(null);
  const [isolatedNodeId, setIsolatedNodeId] = useState<string | null>(null);
  const [range, setRange] = useState(() => {
    const endedAt = new Date();
    return { startedAt: new Date(endedAt.getTime() - windowMs['1h']).toISOString(), endedAt: endedAt.toISOString() };
  });
  const [traces, setTraces] = useState<ApmTraceSummary[]>([]);
  const [tracesLoading, setTracesLoading] = useState(false);

  useEffect(() => {
    getServices().then((services) => {
      const values = Array.from(new Set(services.flatMap((service) => service.environment_views.map((view) => view.environment).filter(Boolean))));
      setEnvironmentOptions(values.sort().map((value) => ({ value, label: value })));
      setServiceIds(new Map(services.map((service) => [`${service.namespace}::${service.name}`, service.id])));
    }).catch(() => setEnvironmentOptions([]));
  }, [getServices]);

  const load = useCallback(async () => {
    setState('loading');
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - windowMs[timeWindow]);
    const nextRange = { startedAt: startedAt.toISOString(), endedAt: endedAt.toISOString() };
    setRange(nextRange);
    try {
      const result = await getTopology({
        started_at: nextRange.startedAt,
        ended_at: nextRange.endedAt,
        environment,
        include_inferred: true,
        status: requestStatus === 'all' ? undefined : requestStatus,
        span_name: spanName.trim() || undefined,
        min_duration_ms: minDurationMs ?? undefined,
      });
      setGraph(result);
      setState(result.nodes.length ? 'ready' : 'empty');
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [environment, getTopology, minDurationMs, requestStatus, spanName, timeWindow]);

  useEffect(() => {
    void load();
  }, [load]);

  const visibleGraph = useMemo(() => {
    const anomalyNodes = graph.nodes.filter((node) => !anomalyOnly || node.health === 'warning' || node.health === 'critical');
    const anomalyIds = new Set(anomalyNodes.map((node) => node.id));
    const anomalyEdges = graph.edges.filter((edge) => anomalyIds.has(edge.source) && anomalyIds.has(edge.target));
    const filtered = filterTopologyByKeyword(anomalyNodes, anomalyEdges, keyword);
    if (!isolatedNodeId) return filtered;
    return isolateTopologyNeighborhood(filtered.nodes, filtered.edges, isolatedNodeId);
  }, [anomalyOnly, graph.edges, graph.nodes, isolatedNodeId, keyword]);

  const anomalyCount = graph.nodes.filter((node) => node.health === 'warning' || node.health === 'critical').length;
  const instrumentedCount = graph.nodes.filter((node) => node.kind !== 'inferred').length;
  const totalCalls = useMemo(() => graph.edges.reduce((sum, edge) => sum + edge.sampled_calls, 0), [graph.edges]);
  const slice = useMemo(
    () => ({
      status: requestStatus === 'all' ? undefined : requestStatus,
      span_name: spanName.trim() || undefined,
      min_duration_ms: minDurationMs ?? undefined,
    }),
    [minDurationMs, requestStatus, spanName],
  );
  const hasSlice = Boolean(slice.status || slice.span_name || slice.min_duration_ms);

  const selectedSamples = useMemo(() => {
    if (selection?.kind === 'node') {
      return visibleGraph.nodes.find((node) => node.id === selection.id)?.sample_traces ?? [];
    }
    if (selection?.kind === 'edge') {
      return visibleGraph.edges.find((edge) => edge.source === selection.source && edge.target === selection.target)?.sample_traces ?? [];
    }
    return [];
  }, [selection, visibleGraph.edges, visibleGraph.nodes]);

  const sampleNode = useMemo(() => {
    if (selection?.kind === 'node') return visibleGraph.nodes.find((node) => node.id === selection.id);
    if (selection?.kind === 'edge') return visibleGraph.nodes.find((node) => node.id === selection.target);
    return undefined;
  }, [selection, visibleGraph.nodes]);

  useEffect(() => {
    if (!sampleNode || selectedSamples.length) {
      setTraces([]);
      setTracesLoading(false);
      return;
    }
    if (sampleNode.kind === 'inferred') {
      setTraces([]);
      setTracesLoading(false);
      return;
    }
    let active = true;
    setTracesLoading(true);
    getTraces({
      service_namespace: sampleNode.service_namespace,
      service_name: sampleNode.service_name,
      environment: sampleNode.environment,
      started_at: range.startedAt,
      ended_at: range.endedAt,
      status: slice.status,
      span_name: slice.span_name,
      min_duration_ms: slice.min_duration_ms,
      limit: 5,
    })
      .then((page) => {
        if (active) setTraces(page.items);
      })
      .catch(() => {
        if (active) setTraces([]);
      })
      .finally(() => {
        if (active) setTracesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getTraces, range.endedAt, range.startedAt, sampleNode, selectedSamples.length, slice.min_duration_ms, slice.span_name, slice.status]);

  return (
    <ApmRouteShell dependency="telemetry" description={t('apm.topology.description', '按时间窗内观测到的 Trace 聚合服务依赖；节点大小表示观测调用量，颜色表示错误率，标签展示 P95。点选节点或边可在右侧查看样本 Trace。未插桩下游以推断节点出现在本页。')} title={t('apm.topology.title', '服务拓扑')}>
      <div className="flex flex-col gap-3">
        {graph.truncated ? <Alert showIcon type="warning" message={t('apm.topology.truncated', '当前拓扑仅聚合查询上限内的最近 Trace，调用量不代表全量流量。')} /> : null}
        {isolatedNodeId ? <Alert showIcon type="info" message={t('apm.topology.isolateBanner', '正在隔离查看一个服务及其直接依赖。')} action={<Button type="link" onClick={() => setIsolatedNodeId(null)}>{t('apm.topology.showFullMap', '显示全图')}</Button>} /> : null}
        <ApmSurface className="overflow-hidden" padding="none">
          <div className="border-b border-[var(--color-border)] p-4">
            <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-1.5 text-xs">
                <strong className="tabular-nums text-sm">{instrumentedCount}</strong><span className="text-[var(--color-text-3)]">{t('apm.common.service', '服务')}</span>
                <span className="text-[var(--color-border)]">·</span>
                <strong className="tabular-nums text-sm">{graph.edges.length}</strong><span className="text-[var(--color-text-3)]">{t('apm.topology.dependency', '依赖')}</span>
                <span className="text-[var(--color-border)]">·</span>
                <strong className="tabular-nums text-sm text-[var(--color-fail)]">{anomalyCount}</strong><span className="text-[var(--color-text-3)]">{t('apm.health.abnormal', '异常')}</span>
                <span className="text-[var(--color-border)]">·</span>
                <strong className="tabular-nums text-sm">{totalCalls}</strong><span className="text-[var(--color-text-3)]">{t('apm.topology.totalCalls', '总调用数')}</span>
              </div>
              <Segmented<TimeWindow> aria-label={t('apm.topology.window', '拓扑时间窗口')} options={['15m', '1h', '4h', '1d', '7d']} value={timeWindow} onChange={setTimeWindow} />
              <Select allowClear aria-label={t('apm.topology.filterEnvironment', '按环境筛选拓扑')} className="w-36" placeholder={t('apm.common.allEnvironments', '全部环境')} options={environmentOptions} value={environment} onChange={setEnvironment} />
              <Select
                allowClear
                aria-label={t('apm.topology.requestStatus', '按请求状态切片')}
                className="w-36"
                options={[
                  { value: 'error', label: t('apm.topology.errorRequestsOnly', '仅错误请求') },
                  { value: 'ok', label: t('apm.topology.okRequestsOnly', '仅正常请求') },
                ]}
                placeholder={t('apm.topology.allRequests', '全部请求')}
                value={requestStatus === 'all' ? undefined : requestStatus}
                onChange={(value) => setRequestStatus(value ?? 'all')}
              />
              <Input
                allowClear
                aria-label={t('apm.topology.filterOperation', '按操作名切片')}
                className="w-40"
                placeholder={t('apm.common.operation', '操作')}
                value={spanName}
                onChange={(event) => setSpanName(event.target.value)}
              />
              <InputNumber
                aria-label={t('apm.topology.minDuration', '耗时下限')}
                className="w-32"
                min={0}
                placeholder={t('apm.topology.minDurationPlaceholder', '耗时下限 ms')}
                value={minDurationMs ?? undefined}
                onChange={(value) => setMinDurationMs(typeof value === 'number' ? value : null)}
              />
              {hasSlice ? (
                <Button onClick={() => { setRequestStatus('all'); setSpanName(''); setMinDurationMs(null); }}>
                  {t('apm.topology.clearSlice', '清空切片')}
                </Button>
              ) : null}
              <Segmented<TopologyLayoutMode>
                aria-label={t('apm.topology.layout', '拓扑布局')}
                className="shrink-0"
                options={[
                  { value: 'layered', label: t('apm.topology.layered', '层次') },
                  { value: 'force', label: t('apm.topology.force', '力导向') },
                ]}
                value={layout}
                onChange={setLayout}
              />
              <Button danger={anomalyOnly} icon={<WarningOutlined aria-hidden="true" />} type={anomalyOnly ? 'primary' : 'default'} onClick={() => setAnomalyOnly((value) => !value)}>{t('apm.topology.anomalyOnly', '只看异常')}</Button>
              <Button aria-label={t('apm.topology.refresh', '刷新拓扑')} icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={() => void load()} />
            </FilterToolbar>
          </div>
          {state === 'ready' ? (
            <div className="flex min-w-0">
              <div className="relative min-w-0 flex-1">
                <TopologyCanvas
                  edges={visibleGraph.edges}
                  layout={layout}
                  nodes={visibleGraph.nodes}
                  selected={selection}
                  toolbar={(
                    <Input
                      allowClear
                      aria-label={t('apm.topology.locate', '定位拓扑节点')}
                      placeholder={t('apm.topology.locatePlaceholder', '定位节点')}
                      prefix={<SearchOutlined aria-hidden="true" />}
                      value={keyword}
                      onChange={(event) => setKeyword(event.target.value)}
                    />
                  )}
                  onSelect={setSelection}
                />
                <div
                  aria-label={t('apm.topology.healthLegend', '节点健康图例')}
                  className="pointer-events-none absolute bottom-3 left-3 z-10 flex items-center gap-x-4 text-xs text-[var(--color-text-3)]"
                  role="list"
                >
                  <TopologyLegendDot color={topologyHealthColors.healthy} label={t('apm.severity.normal', '正常')} />
                  <TopologyLegendDot color={topologyHealthColors.warning} label={t('apm.severity.warning', '警告')} />
                  <TopologyLegendDot color={topologyHealthColors.critical} label={t('apm.severity.critical', '严重')} />
                </div>
              </div>
              <TopologyInspectPanel
                edges={visibleGraph.edges}
                isolated={Boolean(isolatedNodeId)}
                nodes={visibleGraph.nodes}
                selection={selection}
                serviceIds={serviceIds}
                slice={slice}
                startedAt={range.startedAt}
                endedAt={range.endedAt}
                traces={selectedSamples.length ? [] : traces}
                tracesLoading={tracesLoading}
                onIsolate={setIsolatedNodeId}
                onSelectNode={(nodeId) => setSelection({ kind: 'node', id: nodeId })}
                onShowFullMap={() => setIsolatedNodeId(null)}
              />
            </div>
          ) : state === 'empty' ? (
            <div className="min-h-[640px]">
              <CatalogState
                kind="empty"
                description={t('apm.topology.empty', '当前范围内没有观测到可用于构建拓扑的调用链。')}
                onRetry={() => void load()}
              />
            </div>
          ) : <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => void load()} />}
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
