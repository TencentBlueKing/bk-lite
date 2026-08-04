'use client';

import { AimOutlined, MinusOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Segmented, Select, Space, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';

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
}: {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  layout: LayoutMode;
  keyword: string;
  zoom: number;
}) {
  const positionedNodes = positioned(nodes, layout);
  const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
  const normalizedKeyword = keyword.trim().toLowerCase();
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
          const endX = target.x - (dx * 28) / length;
          const endY = target.y - (dy * 28) / length;
          const color = edge.health === 'healthy' || edge.health === 'unknown'
            ? 'var(--color-border-4)'
            : healthColors[edge.health];
          const marker = edge.health === 'unknown' ? 'healthy' : edge.health;
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
                strokeWidth={edge.health === 'critical' ? 2.4 : edge.health === 'warning' ? 1.8 : 1.4}
              />
              <text fill="var(--color-text-3)" fontSize="9" textAnchor="middle" x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 5}>
                {edge.sampled_calls} 次 · {edge.average_duration_ms.toFixed(1)} ms
              </text>
            </g>
          );
        })}
        {positionedNodes.map((node) => {
          const matched = !normalizedKeyword || `${node.service_namespace} ${node.service_name}`.toLowerCase().includes(normalizedKeyword);
          return (
            <g key={node.id} opacity={matched ? 1 : 0.18} transform={`translate(${node.x},${node.y})`}>
              <circle fill="var(--color-bg)" r="25" stroke={healthColors[node.health]} strokeWidth={node.health === 'critical' ? 3 : 2} />
              <text fill="var(--color-text-3)" fontSize="9" fontWeight="600" textAnchor="middle" y="3">SVC</text>
              <text fill={node.health === 'critical' ? 'var(--color-fail)' : 'var(--color-text-1)'} fontSize="11" fontWeight="600" textAnchor="middle" y="42">{node.service_name}</text>
              <text fill="var(--color-text-3)" fontSize="9" textAnchor="middle" y="55">{node.service_namespace || '未归类'} · {node.environment}</text>
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
  const { getServices, getTopology } = useApmApi();
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [state, setState] = useState<PageState>('loading');
  const [layout, setLayout] = useState<LayoutMode>('layered');
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('1h');
  const [environment, setEnvironment] = useState<string>();
  const [environmentOptions, setEnvironmentOptions] = useState<{ value: string; label: string }[]>([]);
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    getServices().then((services) => {
      const values = Array.from(new Set(services.flatMap((service) => service.environment_views.map((view) => view.environment).filter(Boolean))));
      setEnvironmentOptions(values.sort().map((value) => ({ value, label: value })));
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

  return (
    <ApmRouteShell dependency="telemetry" description="从当前组织可见的真实调用链样本聚合服务间依赖关系。" title="服务拓扑">
      <div className="flex flex-col gap-3">
        {graph.truncated ? <Alert showIcon type="warning" message="当前拓扑按有界 Trace 样本聚合；服务或调用链过多时仅展示最近样本。" /> : null}
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs">
            <strong className="tabular-nums text-sm">{graph.nodes.length}</strong><span className="text-[var(--color-text-3)]">服务</span>
            <span>·</span><strong className="tabular-nums text-sm">{graph.edges.length}</strong><span className="text-[var(--color-text-3)]">依赖</span>
            <span>·</span><strong className="tabular-nums text-sm text-[var(--color-fail)]">{anomalyCount}</strong><span className="text-[var(--color-text-3)]">异常</span>
            <span>·</span><strong className="tabular-nums text-sm">{graph.sampled_traces}</strong><span className="text-[var(--color-text-3)]">样本 Trace</span>
          </div>
          <Segmented<TimeWindow> aria-label="拓扑时间窗口" options={['15m', '1h', '4h', '1d', '7d']} value={timeWindow} onChange={setTimeWindow} />
          <Select allowClear aria-label="按环境筛选拓扑" className="w-36" placeholder="全部环境" options={environmentOptions} value={environment} onChange={setEnvironment} />
          <Segmented<LayoutMode> aria-label="拓扑布局" options={[{ value: 'layered', label: '分层' }, { value: 'force', label: '环形' }]} value={layout} onChange={setLayout} />
          <Button danger={anomalyOnly} icon={<WarningOutlined aria-hidden="true" />} type={anomalyOnly ? 'primary' : 'default'} onClick={() => setAnomalyOnly((value) => !value)}>只看异常</Button>
          <Button aria-label="刷新拓扑" icon={<ReloadOutlined aria-hidden="true" />} onClick={() => void load()} />
        </div>
        <ApmSurface className="relative min-h-[520px] overflow-hidden" padding="none">
          {state === 'ready' ? (
            <>
              <div className="absolute left-3 top-3 z-10 flex w-52 flex-col gap-2">
                <Input allowClear aria-label="定位拓扑节点" placeholder="定位节点" prefix={<SearchOutlined aria-hidden="true" />} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                <Space.Compact block>
                  <Button aria-label="放大拓扑" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.min(1.3, value + 0.1))} />
                  <Button aria-label="缩小拓扑" icon={<MinusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.max(0.7, value - 0.1))} />
                  <Button aria-label="重置拓扑缩放" icon={<AimOutlined aria-hidden="true" />} onClick={() => setZoom(1)} />
                </Space.Compact>
              </div>
              <div
                aria-label="服务拓扑画布滚动区域"
                className="overflow-x-auto"
                role="region"
                tabIndex={0}
              >
                <TopologyCanvas edges={visibleEdges} keyword={keyword} layout={layout} nodes={visibleNodes} zoom={zoom} />
              </div>
            </>
          ) : state === 'empty' ? <Empty className="pt-44" description="当前范围内没有可用于构建拓扑的调用链样本。" /> : <CatalogState kind={state} />}
        </ApmSurface>
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[var(--color-text-3)]">
            <LegendDot color={healthColors.healthy} label="正常" /><LegendDot color={healthColors.warning} label="警告" /><LegendDot color={healthColors.critical} label="严重" />
            <Typography.Text type="secondary" className="!text-xs">节点与边的健康状态来自所选时间窗内的有界错误样本，不等同于告警状态。</Typography.Text>
          </div>
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
