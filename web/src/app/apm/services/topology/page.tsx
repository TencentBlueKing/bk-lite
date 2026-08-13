'use client';

import { AimOutlined, MinusOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { Alert, Button, Grid, Input, Segmented, Select, Tag, Typography, type TableColumnsType } from 'antd';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';
import CustomTable from '@/components/custom-table';
import FilterToolbar from '@/components/filter-toolbar';

type LayoutMode = 'layered' | 'force';
type ViewMode = 'graph' | 'list';
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

const healthLabels: Record<ApmTopologyHealth, string> = {
  healthy: '正常',
  warning: '警告',
  critical: '严重',
  unknown: '未知',
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
    <svg aria-label="APM 服务调用拓扑" className="block h-[520px] w-full" role="img" viewBox="0 0 1030 520">
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
              aria-label={`${node.service_name}，${healthLabels[node.health]}，采样 ${node.sampled_spans} 个 Span`}
              opacity={matched ? 1 : 0.18}
              role={onNodeClick ? 'link' : undefined}
              tabIndex={onNodeClick ? 0 : undefined}
              style={{ cursor: onNodeClick ? 'pointer' : undefined }}
              transform={`translate(${node.x},${node.y})`}
              onClick={() => onNodeClick?.(node)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onNodeClick?.(node);
                }
              }}
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
  const screens = Grid.useBreakpoint();
  const { getServices, getTopology } = useApmApi();
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [state, setState] = useState<PageState>('loading');
  const [layout, setLayout] = useState<LayoutMode>('layered');
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
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

  useEffect(() => {
    if (screens.md === false) setViewMode('list');
  }, [screens.md]);

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

  const visibleNodeMap = useMemo(
    () => new Map(visibleNodes.map((node) => [node.id, node])),
    [visibleNodes],
  );
  const dependencyRows = useMemo(() => visibleEdges.flatMap((edge) => {
    const source = visibleNodeMap.get(edge.source);
    const target = visibleNodeMap.get(edge.target);
    return source && target ? [{ ...edge, key: `${edge.source}-${edge.target}`, sourceNode: source, targetNode: target }] : [];
  }), [visibleEdges, visibleNodeMap]);
  type DependencyRow = (typeof dependencyRows)[number];
  const dependencyColumns: TableColumnsType<DependencyRow> = [
    {
      title: '上游服务',
      key: 'source',
      render: (_, row) => (
        <Button className="!h-auto !max-w-full !px-0" type="link" onClick={() => openNode(row.sourceNode)}>
          <span className="truncate">{row.sourceNode.service_name}</span>
        </Button>
      ),
    },
    {
      title: '下游服务',
      key: 'target',
      render: (_, row) => (
        <Button className="!h-auto !max-w-full !px-0" type="link" onClick={() => openNode(row.targetNode)}>
          <span className="truncate">{row.targetNode.service_name}</span>
        </Button>
      ),
    },
    {
      title: '健康',
      dataIndex: 'health',
      width: 90,
      render: (health: ApmTopologyHealth) => (
        <Tag color={health === 'critical' ? 'error' : health === 'warning' ? 'warning' : health === 'healthy' ? 'success' : undefined}>
          {healthLabels[health]}
        </Tag>
      ),
    },
    {
      title: '采样调用',
      dataIndex: 'sampled_calls',
      align: 'right',
      width: 110,
      className: 'tabular-nums',
      responsive: ['sm'],
    },
    {
      title: '平均耗时',
      dataIndex: 'average_duration_ms',
      align: 'right',
      width: 110,
      className: 'tabular-nums',
      render: (value: number) => `${value.toFixed(0)} ms`,
    },
  ];

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
            <Segmented<ViewMode> aria-label="拓扑视图" options={[{ value: 'graph', label: '图形' }, { value: 'list', label: '依赖列表' }]} value={viewMode} onChange={setViewMode} />
            {viewMode === 'graph' ? <Segmented<LayoutMode> aria-label="拓扑布局" options={[{ value: 'layered', label: '分层' }, { value: 'force', label: '力导向' }]} value={layout} onChange={setLayout} /> : null}
            <Button danger={anomalyOnly} icon={<WarningOutlined aria-hidden="true" />} type={anomalyOnly ? 'primary' : 'default'} onClick={() => setAnomalyOnly((value) => !value)}>只看异常</Button>
            <Button aria-label="刷新拓扑" icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={() => void load()} />
          </FilterToolbar>
        </ApmSurface>
        <ApmSurface className={viewMode === 'graph' ? 'relative min-h-[520px] overflow-hidden' : 'overflow-hidden'} padding="none">
          {state === 'ready' ? (
            viewMode === 'graph' ? (
              <>
                <div className="absolute left-3 top-3 z-10 flex w-52 max-w-[calc(100%-24px)] flex-col gap-2">
                  <Input allowClear aria-label="定位拓扑节点" placeholder="定位节点" prefix={<SearchOutlined aria-hidden="true" />} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                  <div className="inline-flex w-fit flex-col overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]">
                    <Button aria-label="放大拓扑" type="text" size="small" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.min(1.3, value + 0.1))} />
                    <Button aria-label="缩小拓扑" type="text" size="small" icon={<MinusOutlined aria-hidden="true" />} onClick={() => setZoom((value) => Math.max(0.7, value - 0.1))} />
                    <Button aria-label="重置拓扑缩放" type="text" size="small" icon={<AimOutlined aria-hidden="true" />} onClick={() => setZoom(1)} />
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
              </>
            ) : (
              <CustomTable
                autoScrollX={false}
                columns={dependencyColumns}
                dataSource={dependencyRows}
                rowKey="key"
                pagination={{
                  defaultPageSize: 20,
                  pageSizeOptions: [10, 20, 50, 100],
                  showSizeChanger: true,
                  showTotal: (total) => `共 ${total} 条依赖`,
                }}
              />
            )
          ) : state === 'empty' ? (
            <CatalogState
              kind="empty"
              description="当前范围内没有可用于构建拓扑的调用链样本。"
              onRetry={() => void load()}
            />
          ) : <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => void load()} />}
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
