'use client';

import { AimOutlined, MinusOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Segmented, Select } from 'antd';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import TopologyCanvas, {
  TopologyLegendDot,
  topologyHealthColors,
  type TopologyLayoutMode,
} from '@/app/apm/services/topology/topology-canvas';
import type { ApmTopologyGraph, ApmTopologyNode } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

export { default as TopologyCanvas } from '@/app/apm/services/topology/topology-canvas';

type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';
type PageState = CatalogStateKind | 'ready';

const windowMs: Record<TimeWindow, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

export default function ApmTopologyPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { getServices, getTopology } = useApmApi();
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [state, setState] = useState<PageState>('loading');
  const [layout, setLayout] = useState<TopologyLayoutMode>('layered');
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('1h');
  const [environment, setEnvironment] = useState<string>();
  const [environmentOptions, setEnvironmentOptions] = useState<{ value: string; label: string }[]>([]);
  const [serviceIds, setServiceIds] = useState<Map<string, string>>(new Map());
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [zoom, setZoom] = useState(1);

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
    try {
      const result = await getTopology({ started_at: startedAt.toISOString(), ended_at: endedAt.toISOString(), environment });
      setGraph(result);
      setState(result.nodes.length ? 'ready' : 'empty');
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [environment, getTopology, timeWindow]);

  useEffect(() => {
    void load();
  }, [load]);

  const visibleNodes = useMemo(() => graph.nodes.filter((node) => !anomalyOnly || node.health === 'warning' || node.health === 'critical'), [anomalyOnly, graph.nodes]);
  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const visibleEdges = useMemo(() => graph.edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)), [graph.edges, visibleNodeIds]);
  const anomalyCount = graph.nodes.filter((node) => node.health === 'warning' || node.health === 'critical').length;
  const totalCalls = useMemo(() => graph.edges.reduce((sum, edge) => sum + edge.sampled_calls, 0), [graph.edges]);

  const openNode = (node: ApmTopologyNode) => {
    const serviceId = serviceIds.get(`${node.service_namespace}::${node.service_name}`);
    if (!serviceId) return;
    const query = node.environment ? `?environment=${encodeURIComponent(node.environment)}` : '';
    router.push(`/apm/services/${serviceId}${query}`);
  };

  return (
    <ApmRouteShell dependency="telemetry" description={t('apm.topology.description', '按时间窗内观测到的 Trace 聚合服务依赖；节点大小表示观测调用量，颜色表示状态。')} title={t('apm.topology.title', '服务拓扑')}>
      <div className="flex flex-col gap-3">
        {graph.truncated ? <Alert showIcon type="warning" message={t('apm.topology.truncated', '当前拓扑仅聚合查询上限内的最近 Trace，调用量不代表全量流量。')} /> : null}
        <ApmSurface className="overflow-hidden" padding="none">
          <div className="border-b border-[var(--color-border)] p-4">
            <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-1.5 text-xs">
                <strong className="tabular-nums text-sm">{graph.nodes.length}</strong><span className="text-[var(--color-text-3)]">{t('apm.common.service', '服务')}</span>
                <span className="text-[var(--color-border)]">·</span>
                <strong className="tabular-nums text-sm">{graph.edges.length}</strong><span className="text-[var(--color-text-3)]">{t('apm.topology.dependency', '依赖')}</span>
                <span className="text-[var(--color-border)]">·</span>
                <strong className="tabular-nums text-sm text-[var(--color-fail)]">{anomalyCount}</strong><span className="text-[var(--color-text-3)]">{t('apm.health.abnormal', '异常')}</span>
                <span className="text-[var(--color-border)]">·</span>
                <strong className="tabular-nums text-sm">{totalCalls}</strong><span className="text-[var(--color-text-3)]">{t('apm.topology.totalCalls', '总调用数')}</span>
              </div>
              <Segmented<TimeWindow> aria-label={t('apm.topology.window', '拓扑时间窗口')} options={['15m', '1h', '4h', '1d', '7d']} value={timeWindow} onChange={setTimeWindow} />
              <Select allowClear aria-label={t('apm.topology.filterEnvironment', '按环境筛选拓扑')} className="w-36" placeholder={t('apm.common.allEnvironments', '全部环境')} options={environmentOptions} value={environment} onChange={setEnvironment} />
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
          <div className="relative min-h-[640px]">
            {state === 'ready' ? (
              <>
                <div className="absolute left-3 top-3 z-10 flex w-52 max-w-[calc(100%-24px)] flex-col gap-2">
                  <Input allowClear aria-label={t('apm.topology.locate', '定位拓扑节点')} placeholder={t('apm.topology.locatePlaceholder', '定位节点')} prefix={<SearchOutlined aria-hidden="true" />} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                  <div className="inline-flex w-fit flex-col overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]">
                    <Button aria-label={t('apm.topology.zoomIn', '放大拓扑')} type="text" size="small" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.min(1.3, value + 0.1))} />
                    <Button aria-label={t('apm.topology.zoomOut', '缩小拓扑')} type="text" size="small" icon={<MinusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.max(0.7, value - 0.1))} />
                    <Button aria-label={t('apm.topology.resetZoom', '重置拓扑缩放')} type="text" size="small" icon={<AimOutlined aria-hidden="true" />} onClick={() => setZoom(1)} />
                  </div>
                </div>
                <TopologyCanvas
                  edges={visibleEdges}
                  keyword={keyword}
                  layout={layout}
                  nodes={visibleNodes}
                  zoom={zoom}
                  onNodeClick={openNode}
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
              </>
            ) : state === 'empty' ? (
              <CatalogState
                kind="empty"
                description={t('apm.topology.empty', '当前范围内没有观测到可用于构建拓扑的调用链。')}
                onRetry={() => void load()}
              />
            ) : <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => void load()} />}
          </div>
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
