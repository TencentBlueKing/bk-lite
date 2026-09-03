'use client';

import { AimOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode, type WheelEvent as ReactWheelEvent } from 'react';
import CatalogState from '@/app/apm/components/catalog-state';
import { formatCompactLatency, formatNumber, topologyMetricParts } from '@/app/apm/components/metric-format';
import { serviceLanguageLabel } from '@/app/apm/components/service-language-icon';
import TopologyServiceIcon from '@/app/apm/components/topology-service-icon';
import {
  buildTopologyEdgeGeometry,
  fitTopologyView,
  hasReciprocalTopologyEdge,
  layoutForceTopology,
  layoutLayeredTopology,
  topologyEntryNameWidth,
  topologyEntryPillWidth,
  topologyNeighborIds,
  topologyNodeNameWidth,
  truncateTopologyNodeLabel,
  TOPOLOGY_CANVAS_SIZE,
  TOPOLOGY_ENTRY_PILL,
  TOPOLOGY_NODE_CARD,
  type PositionedApmTopologyNode,
} from '@/app/apm/services/topology/topology-layout';
import type { ApmTopologyEdge, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

export type TopologyLayoutMode = 'layered' | 'force';

export type TopologyCanvasSelection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; source: string; target: string };

export const MIN_TOPOLOGY_ZOOM = 0.2;
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

const EDGE_STROKE = 'color-mix(in srgb, var(--color-text-3) 48%, var(--color-border))';
const EDGE_STROKE_ACTIVE = 'var(--color-primary)';
const NODE_IDLE_OPACITY = 0.5;
const NODE_DRAG_THRESHOLD_PX = 4;

type CanvasDrag =
  | { kind: 'pan'; startX: number; startY: number; panX: number; panY: number }
  | { kind: 'node'; id: string; startX: number; startY: number; nodeX: number; nodeY: number; k: number; moved: boolean };

const topologyErrorFill = (hasErrors: boolean) => (hasErrors ? topologyHealthColors.critical : 'var(--color-text-3)');

function TopologyMetricLabel({
  errorCount,
  total,
  p95Ms,
  x,
  y,
  fontSize,
  textAnchor = 'start',
  clipPath,
}: {
  errorCount: number;
  total: number;
  p95Ms?: number | null;
  x: number;
  y: number;
  fontSize: number;
  textAnchor?: 'start' | 'middle';
  clipPath?: string;
}) {
  const parts = topologyMetricParts({ errorCount, total, p95_ms: p95Ms });
  const isEdgeLabel = textAnchor === 'middle';
  const pillWidth = 82;
  const pillHeight = fontSize + 8;
  return (
    <g>
      {isEdgeLabel ? (
        <rect
          className="opacity-95"
          fill="var(--color-bg)"
          filter="url(#apm-node-shadow)"
          height={pillHeight}
          rx={6}
          stroke="var(--color-border)"
          strokeWidth="0.8"
          width={pillWidth}
          x={x - pillWidth / 2}
          y={y - pillHeight / 2}
        />
      ) : null}
      <text
        clipPath={clipPath}
        data-topology-metrics="true"
        data-has-errors={!parts.hasErrors ? 'false' : 'true'}
        fontSize={fontSize}
        paintOrder={isEdgeLabel ? undefined : 'stroke'}
        stroke={isEdgeLabel ? undefined : 'var(--color-fill-1)'}
        strokeLinejoin="round"
        strokeWidth={isEdgeLabel ? undefined : '0'}
        textAnchor={textAnchor}
        dominantBaseline={isEdgeLabel ? 'central' : undefined}
        x={x}
        y={isEdgeLabel ? y : y}
      >
        <tspan fill="var(--color-text-3)">{`${parts.total} / ${parts.latency} / `}</tspan>
        <tspan data-error-count="true" fill={topologyErrorFill(parts.hasErrors)} fontWeight={parts.hasErrors ? 700 : undefined}>
          {parts.errors}
        </tspan>
      </text>
    </g>
  );
}

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
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<CanvasDrag | null>(null);
  const skipNodeClickRef = useRef(false);
  const [canvasSize, setCanvasSize] = useState<{ width: number; height: number }>({
    width: TOPOLOGY_CANVAS_SIZE.width,
    height: TOPOLOGY_CANVAS_SIZE.height,
  });
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
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number }>>({});
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const updateSize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w > 0 && h > 0) {
        setCanvasSize((prev) => (prev.width === w && prev.height === h ? prev : { width: w, height: h }));
      }
    };

    updateSize();

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width: w, height: h } = entry.contentRect;
          if (w > 0 && h > 0) {
            const nextW = Math.round(w);
            const nextH = Math.round(h);
            setCanvasSize((prev) => (prev.width === nextW && prev.height === nextH ? prev : { width: nextW, height: nextH }));
          }
        }
      });
      observer.observe(el);
      return () => observer.disconnect();
    }
  }, []);

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
    if (layoutResult.key !== layoutKey) {
      setView({ x: 0, y: 0, k: zoom });
      return;
    }
    const fitted = fitTopologyView(layoutResult.nodes, zoom, canvasSize);
    setView({
      ...fitted,
      k: clampZoom(fitted.k),
    });
  }, [canvasSize, layoutKey, layoutResult, zoom]);

  useEffect(() => {
    setNodePositions({});
    setDraggingNodeId(null);
    dragRef.current = null;
  }, [layoutKey]);

  const layoutPending = layoutResult.key !== layoutKey;
  const positionedNodes = (layoutPending ? [] : layoutResult.nodes).map((node) => {
    const override = nodePositions[node.id];
    return override ? { ...node, x: override.x, y: override.y } : node;
  });
  const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
  const maxSpans = Math.max(...nodes.map((node) => node.sampled_spans), 1);
  const maxCalls = Math.max(...edges.map((edge) => edge.sampled_calls), 1);
  const edgePairs = new Set(edges.map((edge) => edgeKey(edge.source, edge.target)));
  const routing = layout === 'layered' ? 'polyline' : 'curve';
  const focusNodeIds = focusNamespace
    ? new Set(positionedNodes.filter((node) => node.service_namespace === focusNamespace).map((node) => node.id))
    : null;
  const nodeCardWidth = (sampledSpans: number) => TOPOLOGY_NODE_CARD.minWidth + (sampledSpans / maxSpans) * TOPOLOGY_NODE_CARD.widthSpan;
  const nodeVisualRadius = (node: ApmTopologyNode) => (
    node.kind === 'user_request' ? TOPOLOGY_ENTRY_PILL.height / 2 : TOPOLOGY_NODE_CARD.height / 2
  );
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

  const selectNode = (node: ApmTopologyNode) => {
    onSelect?.({ kind: 'node', id: node.id });
    onNodeClick?.(node);
  };

  const viewBoxDelta = (clientX: number, clientY: number, originX: number, originY: number) => {
    const svg = svgRef.current;
    const width = svg?.clientWidth || canvasSize.width;
    const height = svg?.clientHeight || canvasSize.height;
    return {
      dx: (clientX - originX) * (canvasSize.width / width),
      dy: (clientY - originY) * (canvasSize.height / height),
    };
  };

  const applyDragMove = (event: { clientX: number; clientY: number }) => {
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.kind === 'pan') {
      const delta = viewBoxDelta(event.clientX, event.clientY, drag.startX, drag.startY);
      setView((current) => ({ ...current, x: drag.panX + delta.dx, y: drag.panY + delta.dy }));
      return;
    }
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (!drag.moved && distance < NODE_DRAG_THRESHOLD_PX) return;
    drag.moved = true;
    skipNodeClickRef.current = true;
    const delta = viewBoxDelta(event.clientX, event.clientY, drag.startX, drag.startY);
    setNodePositions((current) => ({
      ...current,
      [drag.id]: { x: drag.nodeX + delta.dx / drag.k, y: drag.nodeY + delta.dy / drag.k },
    }));
  };

  const endDrag = () => {
    const drag = dragRef.current;
    dragRef.current = null;
    setDraggingNodeId(null);
    if (drag?.kind === 'node') {
      skipNodeClickRef.current = true;
      const node = nodeMap.get(drag.id);
      if (node) selectNode(node);
    }
  };

  const applyDragMoveRef = useRef(applyDragMove);
  const endDragRef = useRef(endDrag);
  applyDragMoveRef.current = applyDragMove;
  endDragRef.current = endDrag;
  const windowListenersRef = useRef<{ move: (event: MouseEvent) => void; up: () => void } | null>(null);

  const beginWindowDrag = () => {
    if (windowListenersRef.current) return;
    const move = (event: MouseEvent) => applyDragMoveRef.current(event);
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      windowListenersRef.current = null;
      endDragRef.current();
    };
    windowListenersRef.current = { move, up };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  useEffect(() => () => {
    const listeners = windowListenersRef.current;
    if (!listeners) return;
    window.removeEventListener('mousemove', listeners.move);
    window.removeEventListener('mouseup', listeners.up);
    windowListenersRef.current = null;
  }, []);

  const onCanvasMouseDown = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    dragRef.current = { kind: 'pan', startX: event.clientX, startY: event.clientY, panX: view.x, panY: view.y };
    beginWindowDrag();
  };

  const startNodeDrag = (event: ReactMouseEvent<SVGGElement>, node: PositionedApmTopologyNode) => {
    event.stopPropagation();
    if (event.button !== 0) return;
    event.preventDefault();
    skipNodeClickRef.current = false;
    dragRef.current = {
      kind: 'node',
      id: node.id,
      startX: event.clientX,
      startY: event.clientY,
      nodeX: node.x,
      nodeY: node.y,
      k: view.k,
      moved: false,
    };
    setDraggingNodeId(node.id);
    beginWindowDrag();
  };

  const nodeDisplayName = (node: ApmTopologyNode) =>
    node.kind === 'user_request' ? t('apm.topology.userRequestNode', '用户请求') : node.service_name;

  return (
    <div
      ref={containerRef}
      className="relative h-[640px] w-full overflow-hidden bg-[var(--color-fill-1)]"
      data-topology-layout-pending={layoutPending ? 'true' : 'false'}
      data-topology-surface="true"
    >
      {layoutPending ? (
        <div className="absolute inset-0 z-20 flex items-center bg-[var(--color-bg)]/80 backdrop-blur-xs">
          <div className="w-full">
            <CatalogState kind="loading" />
          </div>
        </div>
      ) : null}
      {toolbar ? (
        <div className="absolute left-3.5 top-3.5 z-10 w-60 max-w-[calc(100%-28px)] rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]/95 p-1 shadow-2xs backdrop-blur-md">
          {toolbar}
        </div>
      ) : null}
      <div className={`absolute left-3.5 z-10 flex flex-col gap-2 ${toolbar ? 'top-16' : 'top-3.5'}`}>
        <div className="inline-flex w-fit flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]/95 shadow-2xs backdrop-blur-md">
          <Button aria-label={t('apm.topology.zoomIn', '放大拓扑')} type="text" size="small" icon={<PlusOutlined aria-hidden="true" />} onClick={() => adjustZoom(view.k + 0.15)} />
          <Button aria-label={t('apm.topology.zoomOut', '缩小拓扑')} type="text" size="small" icon={<MinusOutlined aria-hidden="true" />} onClick={() => adjustZoom(view.k - 0.15)} />
          <Button aria-label={t('apm.topology.resetZoom', '重置拓扑缩放')} type="text" size="small" icon={<AimOutlined aria-hidden="true" />} onClick={() => {
            const fitted = fitTopologyView(positionedNodes, zoom, canvasSize);
            setView({ ...fitted, k: clampZoom(fitted.k) });
          }} />
        </div>
      </div>
      <svg
        ref={svgRef}
        aria-label={t('apm.topology.chartAria', 'APM 服务调用拓扑')}
        className="absolute inset-0 block h-full w-full cursor-grab active:cursor-grabbing"
        data-layout={layout}
        data-topology-scale={view.k.toFixed(2)}
        role="img"
        viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
        onWheel={onWheel}
        onMouseDown={onCanvasMouseDown}
        onClick={(event) => {
          if (event.target === event.currentTarget) onSelect?.(null);
        }}
      >
        <defs>
          <pattern
            id="apm-topology-grid"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
            patternTransform={`translate(${view.x % 24} ${view.y % 24})`}
          >
            <circle cx="12" cy="12" r="1.1" fill="var(--color-primary)" opacity="0.14" />
          </pattern>
          <linearGradient id="apm-canvas-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="var(--color-bg)" />
            <stop offset="100%" stopColor="color-mix(in srgb, var(--color-bg) 94%, var(--color-fill-1))" />
          </linearGradient>
          <radialGradient id="apm-canvas-glow" cx="50%" cy="38%" r="65%">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.06" />
            <stop offset="50%" stopColor="var(--color-primary)" stopOpacity="0.015" />
            <stop offset="100%" stopColor="transparent" stopOpacity="0" />
          </radialGradient>
          <filter id="apm-node-shadow" x="-10%" y="-10%" width="124%" height="130%" filterUnits="userSpaceOnUse">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="rgba(0,0,0,0.06)" />
          </filter>
          <marker id="apm-arrow" markerHeight="6" markerUnits="userSpaceOnUse" markerWidth="6" orient="auto" refX="5" refY="3" viewBox="0 0 6 6">
            <path d="M 0 0.6 L 5.5 3 L 0 5.4 Z" fill="context-stroke" strokeLinejoin="round" />
          </marker>
        </defs>
        <rect width="100%" height="100%" fill="url(#apm-canvas-gradient)" pointerEvents="none" />
        <rect width="100%" height="100%" fill="url(#apm-canvas-glow)" pointerEvents="none" />
        <rect width="100%" height="100%" fill="url(#apm-topology-grid)" pointerEvents="none" />
        <g data-topology-view="true" transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
        {edges.map((edge) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return null;
          const geometry = buildTopologyEdgeGeometry(
            { x: source.x, y: source.y, radius: nodeVisualRadius(source) },
            { x: target.x, y: target.y, radius: nodeVisualRadius(target) },
            hasReciprocalTopologyEdge(edge, edgePairs),
            routing,
          );
          const key = edgeKey(edge.source, edge.target);
          const entryEdge = source.kind === 'user_request';
          const isSelected = selectedEdgeKey === key;
          const isHighlighted = highlightedIds
            ? highlightedIds.has(edge.source) && highlightedIds.has(edge.target) && (edge.source === highlightNodeId || edge.target === highlightNodeId)
            : true;
          const color = isSelected
            ? EDGE_STROKE_ACTIVE
            : edge.error_calls > 0
              ? topologyHealthColors.critical
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
              <title>{t('apm.topology.edgeTitle', '{source} 调用 {target}，错误 {errors} 次，共 {calls} 次', {
                source: nodeDisplayName(source),
                target: nodeDisplayName(target),
                errors: formatNumber(edge.error_calls),
                calls: formatNumber(edge.sampled_calls),
              })}</title>
              <path
                d={geometry.path}
                fill="none"
                markerEnd="url(#apm-arrow)"
                stroke={color}
                strokeDasharray={entryEdge ? '5 4' : undefined}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={isSelected ? strokeWidth + 0.6 : strokeWidth}
              />
              <TopologyMetricLabel
                errorCount={edge.error_calls}
                fontSize={10}
                p95Ms={edge.p95_ms}
                textAnchor="middle"
                total={edge.sampled_calls}
                x={geometry.labelX}
                y={geometry.labelY}
              />
            </g>
          );
        })}
        {positionedNodes.map((node, index) => {
          const inferred = node.kind === 'inferred';
          const userRequest = node.kind === 'user_request';
          const nodeName = nodeDisplayName(node);
          const countLabel = formatNumber(node.sampled_spans);
          const cardWidth = userRequest
            ? topologyEntryPillWidth(nodeName, countLabel)
            : nodeCardWidth(node.sampled_spans);
          const cardHeight = userRequest ? TOPOLOGY_ENTRY_PILL.height : TOPOLOGY_NODE_CARD.height;
          const cardRadius = userRequest ? TOPOLOGY_ENTRY_PILL.radius : TOPOLOGY_NODE_CARD.radius;
          const cardX = -cardWidth / 2;
          const cardY = -cardHeight / 2;
          const nameOffsetX = userRequest
            ? TOPOLOGY_ENTRY_PILL.paddingX + TOPOLOGY_ENTRY_PILL.iconSize + TOPOLOGY_ENTRY_PILL.iconGap
            : TOPOLOGY_NODE_CARD.nameOffsetX;
          const inFocus = !focusNodeIds || focusNodeIds.has(node.id);
          const isHighlighted = !highlightedIds || highlightedIds.has(node.id);
          const isSelected = selected?.kind === 'node' && selected.id === node.id;
          const languageTitle = serviceLanguageLabel(node.language, t('apm.language.unknown', '未知'));
          const labelWidth = userRequest
            ? topologyEntryNameWidth(cardWidth, countLabel)
            : topologyNodeNameWidth(cardWidth, inferred);
          const displayName = truncateTopologyNodeLabel(nodeName, labelWidth);
          const inferredBadgeX = cardX + cardWidth - TOPOLOGY_NODE_CARD.healthGutter;
          return (
            <g
              key={node.id}
              aria-label={userRequest
                ? t('apm.topology.userRequestAria', '{name}，时间窗内 {spans} 次请求', {
                  name: nodeName,
                  spans: node.sampled_spans,
                })
                : t('apm.topology.nodeAria', '{name}，{health}，错误 {errors} 次，共 {spans} 次调用，P95 {latency}', {
                  name: nodeName,
                  health: t(topologyHealthI18n[node.health].id, topologyHealthI18n[node.health].fallback),
                  errors: node.error_spans,
                  spans: node.sampled_spans,
                  latency: node.p95_ms == null ? t('apm.common.noData', '无数据') : formatCompactLatency(node.p95_ms),
                })}
              opacity={isHighlighted ? (inFocus ? 1 : 0.62) : NODE_IDLE_OPACITY}
              role="button"
              tabIndex={0}
              data-node-id={node.id}
              data-node-kind={node.kind || 'instrumented'}
              data-peer-address={node.peer_address || undefined}
              data-db-name={node.db_name || undefined}
              data-selected={isSelected ? 'true' : undefined}
              data-node-dragging={draggingNodeId === node.id ? 'true' : undefined}
              className={draggingNodeId === node.id ? 'cursor-grabbing select-none' : 'cursor-grab select-none'}
              transform={`translate(${node.x},${node.y})`}
              onMouseEnter={() => setHoveredNodeId(node.id)}
              onMouseLeave={() => setHoveredNodeId((value) => (value === node.id ? null : value))}
              onMouseDown={(event) => startNodeDrag(event, node)}
              onClick={(event) => {
                event.stopPropagation();
                if (skipNodeClickRef.current) {
                  skipNodeClickRef.current = false;
                  return;
                }
                selectNode(node);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  selectNode(node);
                }
              }}
            >
              <title>{userRequest
                ? t('apm.topology.userRequestTitle', '{name}\n{environment}\n{spans} 次请求', {
                  name: nodeName,
                  environment: node.environment,
                  spans: node.sampled_spans,
                })
                : t('apm.topology.nodeTitle', '{name}\n{language} · {namespace} · {environment}\n错误 {errors} 次 / 共 {spans} 次 · P95 {latency}', {
                  name: nodeName,
                  language: languageTitle,
                  namespace: node.service_namespace || t('apm.common.unsetNamespace', '未设置 namespace'),
                  environment: node.environment,
                  errors: node.error_spans,
                  spans: node.sampled_spans,
                  latency: node.p95_ms == null ? t('apm.common.noData', '无数据') : formatCompactLatency(node.p95_ms),
                })}</title>
              <rect
                data-node-shape={userRequest ? 'entry-pill' : 'service-card'}
                fill={isSelected
                  ? 'var(--color-primary-bg-active)'
                  : userRequest ? 'var(--color-fill-2)' : 'var(--color-bg)'}
                filter="url(#apm-node-shadow)"
                height={cardHeight}
                rx={cardRadius}
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
                size={userRequest ? TOPOLOGY_ENTRY_PILL.iconSize : TOPOLOGY_NODE_CARD.iconSize}
                x={cardX + (userRequest ? TOPOLOGY_ENTRY_PILL.paddingX : TOPOLOGY_NODE_CARD.iconPaddingX)}
                y={userRequest ? -TOPOLOGY_ENTRY_PILL.iconSize / 2 : -TOPOLOGY_NODE_CARD.iconSize / 2}
              />
              <clipPath id={`apm-node-label-${index}`}>
                <rect height={cardHeight} width={labelWidth} x={cardX + nameOffsetX} y={cardY} />
              </clipPath>
              <text
                clipPath={`url(#apm-node-label-${index})`}
                data-node-label="true"
                fill="var(--color-text-1)"
                fontSize="12"
                fontWeight="600"
                textAnchor="start"
                x={cardX + nameOffsetX}
                y={userRequest ? 4 : -3}
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
              {userRequest ? (
                <text
                  className="tabular-nums"
                  data-topology-metrics="true"
                  fill="var(--color-text-3)"
                  fontSize={TOPOLOGY_ENTRY_PILL.countFontSize}
                  textAnchor="end"
                  x={cardX + cardWidth - TOPOLOGY_ENTRY_PILL.paddingX}
                  y={4}
                >
                  {countLabel}
                </text>
              ) : (
                <TopologyMetricLabel
                  clipPath={`url(#apm-node-label-${index})`}
                  errorCount={node.error_spans}
                  fontSize={11}
                  p95Ms={node.p95_ms}
                  total={node.sampled_spans}
                  x={cardX + TOPOLOGY_NODE_CARD.nameOffsetX}
                  y={12}
                />
              )}
              {userRequest ? null : (
                <circle
                  aria-hidden="true"
                  cx={cardX + cardWidth - 12}
                  cy={0}
                  fill={topologyHealthColors[node.health]}
                  r={3.5}
                />
              )}
            </g>
          );
        })}
        </g>
      </svg>
    </div>
  );
}
