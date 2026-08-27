'use client';

import { AimOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode, type WheelEvent as ReactWheelEvent } from 'react';
import { formatCompactLatency, formatErrorRate, formatNumber, formatTopologyEdgeMetrics } from '@/app/apm/components/metric-format';
import { serviceLanguageLabel } from '@/app/apm/components/service-language-icon';
import TopologyServiceIcon from '@/app/apm/components/topology-service-icon';
import {
  buildTopologyEdgeGeometry,
  hasReciprocalTopologyEdge,
  layoutForceTopology,
  layoutLayeredTopology,
  topologyNeighborIds,
  topologyNodeNameWidth,
  truncateTopologyNodeLabel,
  TOPOLOGY_CANVAS_SIZE,
  TOPOLOGY_NODE_CARD,
  type PositionedApmTopologyNode,
} from '@/app/apm/services/topology/topology-layout';
import type { ApmTopologyEdge, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

export type TopologyLayoutMode = 'layered' | 'force';

export type TopologyCanvasSelection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; source: string; target: string };

export const MIN_TOPOLOGY_ZOOM = 0.4;
export const MAX_TOPOLOGY_ZOOM = 2.5;

export const topologyHealthColors: Record<ApmTopologyHealth, string> = {
  healthy: 'var(--color-success)',
  warning: 'var(--theme-color-status-warning)',
  critical: 'var(--color-fail)',
  unknown: 'var(--color-text-4)',
};

export const topologyHealthI18n: Record<ApmTopologyHealth, { id: string; fallback: string }> = {
  healthy: { id: 'apm.severity.normal', fallback: '正常' },
  warning: { id: 'apm.severity.warning', fallback: '警告' },
  critical: { id: 'apm.severity.critical', fallback: '严重' },
  unknown: { id: 'apm.health.unknown', fallback: '未知' },
};

const EDGE_STROKE = 'color-mix(in srgb, var(--color-text-3) 42%, var(--color-border))';
const EDGE_STROKE_ACTIVE = 'var(--color-primary)';
const NODE_IDLE_OPACITY = 0.5;

const clampZoom = (value: number) => Math.min(MAX_TOPOLOGY_ZOOM, Math.max(MIN_TOPOLOGY_ZOOM, value));

const edgeKey = (source: string, target: string) => `${source}\u0000${target}`;

export default function TopologyCanvas({
  nodes,
  edges,
  zoom = 1,
  layout = 'layered',
  focusNamespace,
  selected = null,
  toolbar,
  onSelect,
  onNodeClick,
}: {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  keyword?: string;
  zoom?: number;
  layout?: TopologyLayoutMode;
  focusNamespace?: string;
  selected?: TopologyCanvasSelection | null;
  toolbar?: ReactNode;
  onSelect?: (selection: TopologyCanvasSelection | null) => void;
  onNodeClick?: (node: ApmTopologyNode) => void;
}) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const layoutKey = useMemo(
    () => `${layout}:${nodes.map((node) => node.id).join('|')}:${edges.map((edge) => `${edge.source}>${edge.target}`).join('|')}`,
    [edges, layout, nodes],
  );
  const [layoutResult, setLayoutResult] = useState<{ key: string; nodes: PositionedApmTopologyNode[] }>({
    key: '',
    nodes: [],
  });
  const [view, setView] = useState({ x: 0, y: 0, k: zoom });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const runner = layout === 'force' ? layoutForceTopology : layoutLayeredTopology;
    void runner(nodes, edges)
      .then((result) => {
        if (active) setLayoutResult({ key: layoutKey, nodes: result });
      })
      .catch(() => {
        if (active) setLayoutResult({ key: layoutKey, nodes: [] });
      });

    return () => {
      active = false;
    };
  }, [edges, layout, layoutKey, nodes]);

  useEffect(() => {
    setView({ x: 0, y: 0, k: zoom });
  }, [layoutKey, zoom]);

  const positionedNodes = layoutResult.key === layoutKey ? layoutResult.nodes : [];
  const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
  const maxSpans = Math.max(...nodes.map((node) => node.sampled_spans), 1);
  const maxCalls = Math.max(...edges.map((edge) => edge.sampled_calls), 1);
  const edgePairs = new Set(edges.map((edge) => edgeKey(edge.source, edge.target)));
  const routing = layout === 'layered' ? 'polyline' : 'curve';
  const focusNodeIds = focusNamespace
    ? new Set(positionedNodes.filter((node) => node.service_namespace === focusNamespace).map((node) => node.id))
    : null;
  const nodeCardWidth = (sampledSpans: number) => TOPOLOGY_NODE_CARD.minWidth + (sampledSpans / maxSpans) * TOPOLOGY_NODE_CARD.widthSpan;
  const nodeRadius = () => TOPOLOGY_NODE_CARD.height / 2;
  const highlightNodeId = hoveredNodeId;
  const highlightedIds = highlightNodeId ? topologyNeighborIds(edges, highlightNodeId) : null;
  const selectedEdgeKey = selected?.kind === 'edge' ? edgeKey(selected.source, selected.target) : null;

  const adjustZoom = (next: number, origin?: { x: number; y: number }) => {
    setView((current) => {
      const k = clampZoom(next);
      if (!origin) return { ...current, k };
      const worldX = (origin.x - current.x) / current.k;
      const worldY = (origin.y - current.y) / current.k;
      return { k, x: origin.x - worldX * k, y: origin.y - worldY * k };
    });
  };

  const pointerToSvg = (event: { clientX: number; clientY: number }) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const cursor = point.matrixTransform(ctm.inverse());
    return { x: cursor.x, y: cursor.y };
  };

  const onWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const origin = pointerToSvg(event) ?? undefined;
    adjustZoom(view.k * (event.deltaY > 0 ? 0.9 : 1.1), origin);
  };

  const onMouseDown = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    dragRef.current = { x: event.clientX, y: event.clientY, panX: view.x, panY: view.y };
  };

  const onMouseMove = (event: ReactMouseEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    const svg = svgRef.current;
    if (!drag || !svg) return;
    const width = svg.clientWidth || TOPOLOGY_CANVAS_SIZE.width;
    const height = svg.clientHeight || TOPOLOGY_CANVAS_SIZE.height;
    const dx = (event.clientX - drag.x) * (TOPOLOGY_CANVAS_SIZE.width / width);
    const dy = (event.clientY - drag.y) * (TOPOLOGY_CANVAS_SIZE.height / height);
    setView((current) => ({ ...current, x: drag.panX + dx, y: drag.panY + dy }));
  };

  const endDrag = () => {
    dragRef.current = null;
  };

  const selectNode = (node: ApmTopologyNode) => {
    onSelect?.({ kind: 'node', id: node.id });
    onNodeClick?.(node);
  };

  const nodeMetricLine = (node: ApmTopologyNode) => {
    const latency = node.p95_ms == null ? t('apm.common.noData', '无数据') : formatCompactLatency(node.p95_ms);
    const errorRate = node.error_rate == null ? null : formatErrorRate(node.error_rate);
    return errorRate ? `${latency} · ${errorRate}` : latency;
  };

  return (
    <div className="relative h-[640px] w-full overflow-hidden bg-[var(--color-fill-1)]" data-topology-surface="true">
      {toolbar ? <div className="absolute left-3 top-3 z-10 w-52 max-w-[calc(100%-24px)]">{toolbar}</div> : null}
      <div className={`absolute left-3 z-10 inline-flex w-fit flex-col overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] ${toolbar ? 'top-14' : 'top-3'}`}>
        <Button aria-label={t('apm.topology.zoomIn', '放大拓扑')} type="text" size="small" icon={<PlusOutlined aria-hidden="true" />} onClick={() => adjustZoom(view.k + 0.15)} />
        <Button aria-label={t('apm.topology.zoomOut', '缩小拓扑')} type="text" size="small" icon={<MinusOutlined aria-hidden="true" />} onClick={() => adjustZoom(view.k - 0.15)} />
        <Button aria-label={t('apm.topology.resetZoom', '重置拓扑缩放')} type="text" size="small" icon={<AimOutlined aria-hidden="true" />} onClick={() => setView({ x: 0, y: 0, k: 1 })} />
      </div>
      <svg
        ref={svgRef}
        aria-label={t('apm.topology.chartAria', 'APM 服务调用拓扑')}
        className="absolute inset-0 block h-full w-full cursor-grab active:cursor-grabbing"
        data-layout={layout}
        data-topology-scale={view.k.toFixed(2)}
        role="img"
        viewBox={`0 0 ${TOPOLOGY_CANVAS_SIZE.width} ${TOPOLOGY_CANVAS_SIZE.height}`}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
        onClick={(event) => {
          if (event.target === event.currentTarget) onSelect?.(null);
        }}
      >
        <defs>
          <marker id="apm-arrow" markerHeight="6" markerUnits="userSpaceOnUse" markerWidth="6" orient="auto" refX="5" refY="3" viewBox="0 0 6 6">
            <path d="M 0 0.6 L 5.5 3 L 0 5.4 Z" fill="context-stroke" />
          </marker>
        </defs>
        <g data-topology-view="true" transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
        {edges.map((edge) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return null;
          const geometry = buildTopologyEdgeGeometry(
            { x: source.x, y: source.y, radius: nodeRadius() },
            { x: target.x, y: target.y, radius: nodeRadius() },
            hasReciprocalTopologyEdge(edge, edgePairs),
            routing,
          );
          const key = edgeKey(edge.source, edge.target);
          const isSelected = selectedEdgeKey === key;
          const isHighlighted = highlightedIds
            ? highlightedIds.has(edge.source) && highlightedIds.has(edge.target) && (edge.source === highlightNodeId || edge.target === highlightNodeId)
            : true;
          const color = isSelected
            ? EDGE_STROKE_ACTIVE
            : edge.health === 'critical'
              ? topologyHealthColors.critical
              : edge.health === 'warning'
                ? topologyHealthColors.warning
                : EDGE_STROKE;
          const strokeWidth = Math.max(1, Math.min(2.4, 0.9 + (edge.sampled_calls / maxCalls) * 1.4));
          return (
            <g
              data-source={edge.source}
              data-target={edge.target}
              data-selected={isSelected ? 'true' : undefined}
              key={`${edge.source}-${edge.target}`}
              opacity={isHighlighted ? 1 : NODE_IDLE_OPACITY}
              role={onSelect ? 'button' : undefined}
              tabIndex={onSelect ? 0 : undefined}
              className={onSelect ? 'cursor-pointer' : undefined}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onSelect?.({ kind: 'edge', source: edge.source, target: edge.target });
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect?.({ kind: 'edge', source: edge.source, target: edge.target });
                }
              }}
            >
              <title>{t('apm.topology.edgeTitle', '{source} 调用 {target}，观测调用 {calls} 次', {
                source: source.service_name,
                target: target.service_name,
                calls: formatNumber(edge.sampled_calls),
              })}</title>
              <path
                d={geometry.path}
                fill="none"
                markerEnd="url(#apm-arrow)"
                stroke={color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={isSelected ? strokeWidth + 0.6 : strokeWidth}
              />
              <text
                fill="var(--color-text-3)"
                fontSize="10"
                paintOrder="stroke"
                stroke="var(--color-fill-1)"
                strokeLinejoin="round"
                strokeWidth="4"
                textAnchor="middle"
                x={geometry.labelX}
                y={geometry.labelY - 6}
              >
                {formatTopologyEdgeMetrics(edge)}
              </text>
            </g>
          );
        })}
        {positionedNodes.map((node, index) => {
          const cardWidth = nodeCardWidth(node.sampled_spans);
          const cardHeight = TOPOLOGY_NODE_CARD.height;
          const cardX = -cardWidth / 2;
          const cardY = -cardHeight / 2;
          const inFocus = !focusNodeIds || focusNodeIds.has(node.id);
          const isHighlighted = !highlightedIds || highlightedIds.has(node.id);
          const isSelected = selected?.kind === 'node' && selected.id === node.id;
          const languageTitle = serviceLanguageLabel(node.language, t('apm.language.unknown', '未知'));
          const inferred = node.kind === 'inferred';
          const labelWidth = topologyNodeNameWidth(cardWidth, inferred);
          const displayName = truncateTopologyNodeLabel(node.service_name, labelWidth);
          const inferredBadgeX = cardX + cardWidth - TOPOLOGY_NODE_CARD.healthGutter;
          return (
            <g
              key={node.id}
              aria-label={t('apm.topology.nodeAria', '{name}，{health}，P95 {latency}，时间窗内观测 {spans} 次调用', {
                name: node.service_name,
                health: t(topologyHealthI18n[node.health].id, topologyHealthI18n[node.health].fallback),
                latency: node.p95_ms == null ? t('apm.common.noData', '无数据') : formatCompactLatency(node.p95_ms),
                spans: node.sampled_spans,
              })}
              opacity={isHighlighted ? (inFocus ? 1 : 0.62) : NODE_IDLE_OPACITY}
              role={onSelect || onNodeClick ? 'button' : undefined}
              tabIndex={onSelect || onNodeClick ? 0 : undefined}
              data-node-id={node.id}
              data-node-kind={node.kind || 'instrumented'}
              data-peer-address={node.peer_address || undefined}
              data-db-name={node.db_name || undefined}
              data-selected={isSelected ? 'true' : undefined}
              className={onSelect || onNodeClick ? 'cursor-pointer' : undefined}
              transform={`translate(${node.x},${node.y})`}
              onMouseEnter={() => setHoveredNodeId(node.id)}
              onMouseLeave={() => setHoveredNodeId((value) => (value === node.id ? null : value))}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                selectNode(node);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  selectNode(node);
                }
              }}
            >
              <title>{t('apm.topology.nodeTitle', '{name}\n{language} · {namespace} · {environment}\nP95 {latency} · 错误率 {errors} · 观测调用 {spans}', {
                name: node.service_name,
                language: languageTitle,
                namespace: node.service_namespace || t('apm.common.unsetNamespace', '未设置 namespace'),
                environment: node.environment,
                latency: node.p95_ms == null ? t('apm.common.noData', '无数据') : formatCompactLatency(node.p95_ms),
                errors: node.error_rate == null ? t('apm.common.noData', '无数据') : formatErrorRate(node.error_rate),
                spans: node.sampled_spans,
              })}</title>
              <rect
                fill={isSelected ? 'var(--color-primary-bg-active)' : 'var(--color-bg)'}
                height={cardHeight}
                rx={TOPOLOGY_NODE_CARD.radius}
                stroke={isSelected ? 'var(--color-primary)' : 'var(--color-border)'}
                strokeDasharray={inferred ? '4 3' : undefined}
                strokeWidth={isSelected ? 1.5 : 1}
                width={cardWidth}
                x={cardX}
                y={cardY}
              />
              <TopologyServiceIcon
                inferredSystem={node.inferred_system}
                kind={node.kind}
                language={node.language}
                serviceName={node.service_name}
                size={14}
                x={cardX + 10}
                y={-7}
              />
              <clipPath id={`apm-node-label-${index}`}>
                <rect height={cardHeight} width={labelWidth} x={cardX + TOPOLOGY_NODE_CARD.nameOffsetX} y={cardY} />
              </clipPath>
              <text
                clipPath={`url(#apm-node-label-${index})`}
                data-node-label="true"
                fill="var(--color-text-1)"
                fontSize="12"
                fontWeight="600"
                textAnchor="start"
                x={cardX + TOPOLOGY_NODE_CARD.nameOffsetX}
                y={-3}
              >
                {displayName}
              </text>
              {inferred ? (
                <text
                  fill="var(--color-text-3)"
                  fontSize="9"
                  textAnchor="end"
                  x={inferredBadgeX}
                  y={-8}
                >
                  {t('apm.topology.inferredBadge', '推断')}
                </text>
              ) : null}
              <text
                clipPath={`url(#apm-node-label-${index})`}
                fill="var(--color-text-3)"
                fontSize="11"
                textAnchor="start"
                x={cardX + TOPOLOGY_NODE_CARD.nameOffsetX}
                y={12}
              >
                {nodeMetricLine(node)}
              </text>
              <circle
                aria-hidden="true"
                cx={cardX + cardWidth - 12}
                cy={0}
                fill={topologyHealthColors[node.health]}
                r={3.5}
              />
            </g>
          );
        })}
        </g>
      </svg>
    </div>
  );
}

export function TopologyLegendDot({ color, label }: { color: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: color }} /><span>{label}</span></span>;
}
