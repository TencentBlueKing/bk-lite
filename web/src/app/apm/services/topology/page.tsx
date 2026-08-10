'use client';

import { AimOutlined, MinusOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Segmented, Select, Typography } from 'antd';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';

type LayoutMode = 'layered' | 'force';
type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';
type PageState = CatalogStateKind | 'ready';

const windowMs: Record<TimeWindow, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

const healthColors: Record<ApmTopologyHealth, string> = {
  healthy: 'var(--color-success)',
  warning: 'var(--theme-color-status-warning)',
  critical: 'var(--color-fail)',
  unknown: 'var(--color-text-4)',
};

function positioned(nodes: ApmTopologyNode[], layout: LayoutMode) {
  return nodes.map((node, index) => {
    if (layout === 'layered') {
      return { ...node, x: 130 + (index % 5) * 190, y: 105 + Math.floor(index / 5) * 145 };
    }
    const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
    const radius = 150 + (index % 3) * 45;
    return { ...node, x: 515 + Math.cos(angle) * radius, y: 260 + Math.sin(angle) * radius };
  });
}

function TopologyCanvas({
  nodes,
  edges,
  layout,
  keyword,
  zoom,
  onNodeClick,
}: {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  layout: LayoutMode;
  keyword: string;
  zoom: number;
  onNodeClick?: (node: ApmTopologyNode) => void;
}) {
  const positionedNodes = positioned(nodes, layout);
  const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
  const normalizedKeyword = keyword.trim().toLowerCase();
  const maxSpans = Math.max(...nodes.map((node) => node.sampled_spans), 1);
  return (
    <svg aria-label="APM 服务调用拓扑" className="block h-[520px] min-w-[960px] w-full" role="img" viewBox="0 0 1030 520">
      <defs>
        {(['healthy', 'warning', 'critical'] as ApmTopologyHealth[]).map((health) => (
          <marker id={`apm-arrow-${health}`} key={health} markerHeight="6" markerWidth="6" orient="auto" refX="9" refY="5" viewBox="0 0 10 10">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        ))}
      </defs>
      <g style={{ transform: `scale(${zoom})`, transformBox: 'fill-box', transformOrigin: 'center' }}>
        {edges.map((edge) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return null;
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const length = Math.sqrt(dx * dx + dy * dy) || 1;
          const targetRadius = 18 + (target.sampled_spans / maxSpans) * 14;
          const endX = target.x - (dx * (targetRadius + 4)) / length;
          const endY = target.y - (dy * (targetRadius + 4)) / length;
          const color = edge.health === 'healthy' || edge.health === 'unknown'
            ? 'var(--color-border-4)'
            : healthColors[edge.health];
          const marker = edge.health === 'unknown' ? 'healthy' : edge.health;
          const strokeWidth = Math.max(1.2, Math.min(3.2, 1 + (edge.sampled_calls / Math.max(...edges.map((item) => item.sampled_calls), 1)) * 2));
          return (
            <g key={`${edge.source}-${edge.target}`}>
              <line
                x1={source.x}
                y1={source.y}
                x2={endX}
                y2={endY}
                markerEnd={`url(#apm-arrow-${marker})`}
                stroke={color}
                strokeDasharray={edge.health === 'critical' ? '6 4' : undefined}
                strokeWidth={strokeWidth}
              />
              <text fill="var(--color-text-3)" fontSize="9" textAnchor="middle" x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 5}>
                {edge.sampled_calls} · {edge.average_duration_ms.toFixed(0)}ms
              </text>
            </g>
          );
        })}
        {positionedNodes.map((node) => {
          const matched = !normalizedKeyword || `${node.service_namespace} ${node.service_name}`.toLowerCase().includes(normalizedKeyword);
          const radius = 18 + (node.sampled_spans / maxSpans) * 14;
          return (
            <g
              key={node.id}
              opacity={matched ? 1 : 0.18}
              style={{ cursor: onNodeClick ? 'pointer' : undefined }}
              transform={`translate(${node.x},${node.y})`}
              onClick={() => onNodeClick?.(node)}
            >
              <title>{`${node.service_name}\n吞吐采样 ${node.sampled_spans} · 错误 ${node.error_spans}`}</title>
              <circle
                fill={node.health === 'critical'
                  ? 'color-mix(in srgb, var(--color-fail) 12%, var(--color-bg))'
                  : node.health === 'warning'
                    ? 'color-mix(in srgb, var(--theme-color-status-warning) 12%, var(--color-bg))'
                    : 'var(--color-bg)'}
                r={radius}
                stroke={healthColors[node.health]}
                strokeWidth={node.health === 'critical' ? 3 : 2}
              />
              <text fill="var(--color-text-3)" fontSize="9" fontWeight="600" textAnchor="middle" y="3">SVC</text>
              <text
                fill={node.health === 'critical' ? 'var(--color-fail)' : 'var(--color-text-1)'}
                fontSize="11"
                fontWeight="600"
                textAnchor="middle"
                y={radius + 16}
              >
                {node.service_name}
              </text>
              <text fill="var(--color-text-3)" fontSize="9" textAnchor="middle" y={radius + 29}>
                {node.service_namespace || '未归类'} · {node.environment}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: color }} /><span>{label}</span></span>;
}

export default function ApmTopologyPage() {
  const router = useRouter();
  const { getServices, getTopology } = useApmApi();
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [state, setState] = useState<PageState>('loading');
  const [layout, setLayout] = useState<LayoutMode>('layered');
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

  const openNode = (node: ApmTopologyNode) => {
    const serviceId = serviceIds.get(`${node.service_namespace}::${node.service_name}`);
    if (!serviceId) return;
    const query = node.environment ? `?environment=${encodeURIComponent(node.environment)}` : '';
    router.push(`/apm/services/${serviceId}${query}`);
  };

  return (
    <ApmRouteShell dependency="telemetry" description="按近窗 Trace 样本聚合服务依赖；节点大小表示采样吞吐，颜色表示健康。" title="服务拓扑">
      <div className="flex flex-col gap-3">
        {graph.truncated ? <Alert showIcon type="warning" message="当前拓扑按有界 Trace 样本聚合；服务或调用链过多时仅展示最近样本。" /> : null}
        <ApmSurface padding="compact">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-1.5 text-xs">
              <strong className="tabular-nums text-sm">{graph.nodes.length}</strong><span className="text-[var(--color-text-3)]">服务</span>
              <span className="text-[var(--color-border)]">·</span>
              <strong className="tabular-nums text-sm">{graph.edges.length}</strong><span className="text-[var(--color-text-3)]">依赖</span>
              <span className="text-[var(--color-border)]">·</span>
              <strong className="tabular-nums text-sm text-[var(--color-fail)]">{anomalyCount}</strong><span className="text-[var(--color-text-3)]">异常</span>
              <span className="text-[var(--color-border)]">·</span>
              <strong className="tabular-nums text-sm">{graph.sampled_traces}</strong><span className="text-[var(--color-text-3)]">样本</span>
            </div>
            <Segmented<TimeWindow> aria-label="拓扑时间窗口" options={['15m', '1h', '4h', '1d', '7d']} value={timeWindow} onChange={setTimeWindow} />
            <Select allowClear aria-label="按环境筛选拓扑" className="w-36" placeholder="全部环境" options={environmentOptions} value={environment} onChange={setEnvironment} />
            <Segmented<LayoutMode> aria-label="拓扑布局" options={[{ value: 'layered', label: '分层' }, { value: 'force', label: '力导向' }]} value={layout} onChange={setLayout} />
            <Button danger={anomalyOnly} icon={<WarningOutlined aria-hidden="true" />} type={anomalyOnly ? 'primary' : 'default'} onClick={() => setAnomalyOnly((value) => !value)}>只看异常</Button>
            <Button aria-label="刷新拓扑" icon={<ReloadOutlined aria-hidden="true" />} onClick={() => void load()} />
          </FilterToolbar>
        </ApmSurface>
        <ApmSurface className="relative min-h-[520px] overflow-hidden" padding="none">
          {state === 'ready' ? (
            <>
              <div className="absolute left-3 top-3 z-10 flex w-52 flex-col gap-2">
                <Input allowClear aria-label="定位拓扑节点" placeholder="定位节点" prefix={<SearchOutlined aria-hidden="true" />} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                <div className="inline-flex w-fit flex-col overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]">
                  <Button aria-label="放大拓扑" type="text" size="small" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.min(1.3, value + 0.1))} />
                  <Button aria-label="缩小拓扑" type="text" size="small" icon={<MinusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.max(0.7, value - 0.1))} />
                  <Button aria-label="重置拓扑缩放" type="text" size="small" icon={<AimOutlined aria-hidden="true" />} onClick={() => setZoom(1)} />
                </div>
              </div>
              <div
                aria-label="服务拓扑画布滚动区域"
                className="overflow-x-auto"
                role="region"
                tabIndex={0}
              >
                <TopologyCanvas
                  edges={visibleEdges}
                  keyword={keyword}
                  layout={layout}
                  nodes={visibleNodes}
                  zoom={zoom}
                  onNodeClick={openNode}
                />
              </div>
            </>
          ) : state === 'empty' ? <Empty className="pt-44" description="当前范围内没有可用于构建拓扑的调用链样本。" /> : <CatalogState kind={state} />}
        </ApmSurface>
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[var(--color-text-3)]">
            <LegendDot color={healthColors.healthy} label="正常" />
            <LegendDot color={healthColors.warning} label="警告" />
            <LegendDot color={healthColors.critical} label="严重" />
            <Typography.Text type="secondary" className="!text-xs">节点大小按采样吞吐缩放；点击节点进入服务详情。</Typography.Text>
          </div>
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
