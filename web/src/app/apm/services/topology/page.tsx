'use client';

import { AimOutlined, MinusOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { Alert, Button, Grid, Input, Segmented, Select, Tag, Typography, type TableColumnsType } from 'antd';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

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

const topologyHealthI18n: Record<ApmTopologyHealth, { id: string; fallback: string }> = {
  healthy: { id: 'apm.severity.normal', fallback: '正常' },
  warning: { id: 'apm.severity.warning', fallback: '警告' },
  critical: { id: 'apm.severity.critical', fallback: '严重' },
  unknown: { id: 'apm.health.unknown', fallback: '未知' },
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
  const { t } = useTranslation();
  const positionedNodes = positioned(nodes, layout);
  const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
  const normalizedKeyword = keyword.trim().toLowerCase();
  const maxSpans = Math.max(...nodes.map((node) => node.sampled_spans), 1);
  return (
    <svg aria-label={t('apm.topology.chartAria', 'APM 服务调用拓扑')} className="block h-[520px] w-full" role="img" viewBox="0 0 1030 520">
      <defs>
        {(['healthy', 'warning', 'critical'] as ApmTopologyHealth[]).map((health) => (
          <marker id={`apm-arrow-${health}`} key={health} markerHeight="8" markerUnits="userSpaceOnUse" markerWidth="8" orient="auto" refX="7" refY="4" viewBox="0 0 8 8">
            <path d="M 0 0 L 8 4 L 0 8 Z" fill="context-stroke" />
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
          const sourceRadius = 18 + (source.sampled_spans / maxSpans) * 14;
          const startX = source.x + (dx * (sourceRadius + 4)) / length;
          const startY = source.y + (dy * (sourceRadius + 4)) / length;
          const endX = target.x - (dx * (targetRadius + 9)) / length;
          const endY = target.y - (dy * (targetRadius + 9)) / length;
          const color = edge.health === 'healthy' || edge.health === 'unknown'
            ? 'var(--color-border-4)'
            : healthColors[edge.health];
          const marker = edge.health === 'unknown' ? 'healthy' : edge.health;
          const strokeWidth = Math.max(1.2, Math.min(3.2, 1 + (edge.sampled_calls / Math.max(...edges.map((item) => item.sampled_calls), 1)) * 2));
          return (
            <g key={`${edge.source}-${edge.target}`}>
              <line
                x1={startX}
                y1={startY}
                x2={endX}
                y2={endY}
                markerEnd={`url(#apm-arrow-${marker})`}
                stroke={color}
                strokeDasharray={edge.health === 'critical' ? '6 4' : undefined}
                strokeWidth={strokeWidth}
              />
              <text fill="var(--color-text-3)" fontSize="10" textAnchor="middle" x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 5}>
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
              aria-label={t('apm.topology.nodeAria', '{name}，{health}，时间窗内观测 {spans} 个 Span', {
                name: node.service_name,
                health: t(topologyHealthI18n[node.health].id, topologyHealthI18n[node.health].fallback),
                spans: node.sampled_spans,
              })}
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
              <title>{t('apm.topology.nodeTitle', '{name}\n观测 Span {spans} · 错误 {errors}', {
                name: node.service_name,
                spans: node.sampled_spans,
                errors: node.error_spans,
              })}</title>
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
              <text fill="var(--color-text-3)" fontSize="10" fontWeight="600" textAnchor="middle" y="3">{t('apm.common.service', '服务')}</text>
              <text
                fill={node.health === 'critical' ? 'var(--color-fail)' : 'var(--color-text-1)'}
                fontSize="11"
                fontWeight="600"
                textAnchor="middle"
                y={radius + 16}
              >
                {node.service_name}
              </text>
              <text fill="var(--color-text-3)" fontSize="10" textAnchor="middle" y={radius + 29}>
                {node.service_namespace || t('apm.common.unsetNamespace', '未设置 namespace')} · {node.environment}
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
  const { t } = useTranslation();
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
      title: t('apm.topology.upstream', '上游服务'),
      key: 'source',
      render: (_, row) => (
        <Button className="!h-auto !max-w-full !px-0" type="link" onClick={() => openNode(row.sourceNode)}>
          <span className="truncate">{row.sourceNode.service_name}</span>
        </Button>
      ),
    },
    {
      title: t('apm.topology.downstream', '下游服务'),
      key: 'target',
      render: (_, row) => (
        <Button className="!h-auto !max-w-full !px-0" type="link" onClick={() => openNode(row.targetNode)}>
          <span className="truncate">{row.targetNode.service_name}</span>
        </Button>
      ),
    },
    {
      title: t('apm.topology.health', '健康'),
      dataIndex: 'health',
      width: 90,
      align: 'center',
      responsive: ['sm'],
      render: (health: ApmTopologyHealth) => (
        <Tag color={health === 'critical' ? 'error' : health === 'warning' ? 'warning' : health === 'healthy' ? 'success' : undefined}>
          {t(topologyHealthI18n[health].id, topologyHealthI18n[health].fallback)}
        </Tag>
      ),
    },
    {
      title: t('apm.topology.observedCalls', '观测调用'),
      dataIndex: 'sampled_calls',
      align: 'right',
      width: 110,
      className: 'tabular-nums',
      responsive: ['lg'],
    },
    {
      title: t('apm.topology.avgDuration', '平均耗时'),
      dataIndex: 'average_duration_ms',
      align: 'right',
      width: 110,
      className: 'tabular-nums',
      responsive: ['md'],
      render: (value: number) => `${value.toFixed(0)} ms`,
    },
  ];

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
                <strong className="tabular-nums text-sm">{graph.sampled_traces}</strong><span className="text-[var(--color-text-3)]">{t('apm.topology.observedTraces', '观测 Trace')}</span>
              </div>
              <Segmented<TimeWindow> aria-label={t('apm.topology.window', '拓扑时间窗口')} options={['15m', '1h', '4h', '1d', '7d']} value={timeWindow} onChange={setTimeWindow} />
              <Select allowClear aria-label={t('apm.topology.filterEnvironment', '按环境筛选拓扑')} className="w-36" placeholder={t('apm.common.allEnvironments', '全部环境')} options={environmentOptions} value={environment} onChange={setEnvironment} />
              <Segmented<ViewMode> aria-label={t('apm.topology.view', '拓扑视图')} options={[{ value: 'graph', label: t('apm.topology.graph', '图形') }, { value: 'list', label: t('apm.topology.list', '依赖列表') }]} value={viewMode} onChange={setViewMode} />
              {viewMode === 'graph' ? <Segmented<LayoutMode> aria-label={t('apm.topology.layout', '拓扑布局')} options={[{ value: 'layered', label: t('apm.topology.layered', '分层') }, { value: 'force', label: t('apm.topology.force', '力导向') }]} value={layout} onChange={setLayout} /> : null}
              <Button danger={anomalyOnly} icon={<WarningOutlined aria-hidden="true" />} type={anomalyOnly ? 'primary' : 'default'} onClick={() => setAnomalyOnly((value) => !value)}>{t('apm.topology.anomalyOnly', '只看异常')}</Button>
              <Button aria-label={t('apm.topology.refresh', '刷新拓扑')} icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={() => void load()} />
            </FilterToolbar>
          </div>
          <div className={viewMode === 'graph' ? 'relative min-h-[520px]' : ''}>
            {state === 'ready' ? (
              viewMode === 'graph' ? (
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
                </>
              ) : (
                <div className="p-4">
                  <ApmDataTable
                    columns={dependencyColumns}
                    dataSource={dependencyRows}
                    rowKey="key"
                    pagination={{
                      defaultPageSize: 20,
                      pageSizeOptions: [10, 20, 50, 100],
                      showSizeChanger: true,
                      showTotal: (total) => t('apm.common.paginationTotalDeps', '共 {total} 条依赖', { total }),
                    }}
                  />
                </div>
              )
            ) : state === 'empty' ? (
              <CatalogState
                kind="empty"
                description={t('apm.topology.empty', '当前范围内没有观测到可用于构建拓扑的调用链。')}
                onRetry={() => void load()}
              />
            ) : <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => void load()} />}
          </div>
        </ApmSurface>
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[var(--color-text-3)]">
            <LegendDot color={healthColors.healthy} label={t('apm.severity.normal', '正常')} />
            <LegendDot color={healthColors.warning} label={t('apm.severity.warning', '警告')} />
            <LegendDot color={healthColors.critical} label={t('apm.severity.critical', '严重')} />
            <Typography.Text type="secondary" className="!text-xs">{t('apm.topology.legendHint', '观测数据是时间窗内有界查询结果；点击节点进入服务详情。')}</Typography.Text>
          </div>
        </ApmSurface>
      </div>
    </ApmRouteShell>
  );
}
