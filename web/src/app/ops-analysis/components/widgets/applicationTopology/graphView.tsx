'use client';

import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button, Tooltip } from 'antd';
import {
  FullscreenOutlined,
  ReloadOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getIconUrl } from '@/app/cmdb/utils/modelIcon';
import { relatedTopologyCanvasStyle } from '@/app/ops-analysis/components/widgets/relatedTopology/visual';
import {
  APPLICATION_TOPOLOGY_LAYOUT,
  APPLICATION_TOPOLOGY_NODE,
  applicationTopologyToneColor,
  buildApplicationTopologyLayout,
  resolveApplicationTopologyHover,
  type ApplicationTopologyBandNode,
  type ApplicationTopologyEdge,
  type ApplicationTopologyHover,
  type ApplicationTopologySourceLink,
  type ApplicationTopologySourceNode,
  type ApplicationTopologyTone,
} from './bandModel';
import ApplicationTopologyDetailPanel from './detailPanel';
import {
  APPLICATION_TOPOLOGY_LAYER_LABEL_FONT,
  APPLICATION_TOPOLOGY_LEGEND_FONT,
  APPLICATION_TOPOLOGY_SCALE,
  applicationTopologyChromeScale,
  applicationTopologyLabelRailWidth,
  fitApplicationTopologyLayers,
  zoomApplicationTopologyAt,
} from './viewport';

const LAYER_LABEL_KEY: Record<ApplicationTopologyBandNode['layer'], string> = {
  root: 'dashboard.applicationTopologyLayerSystem',
  service: 'dashboard.applicationTopologyLayerService',
  host: 'dashboard.applicationTopologyLayerHost',
  appService: 'dashboard.applicationTopologyLayerAppService',
  infrastructure: 'dashboard.applicationTopologyLayerInfrastructure',
};

/** 五字层名靠右排进这一列，避免再压到节点上。 */
const LAYER_LABEL_RAIL_PX = 96;

const HOVER_COLOR = 'color-mix(in srgb, var(--color-primary) 72%, var(--color-bg))';

const CATEGORY_LABEL_KEY: Record<string, string> = {
  application: 'dashboard.applicationTopologyGroupApplication',
  host: 'dashboard.applicationTopologyGroupHost',
  database: 'dashboard.applicationTopologyGroupDatabase',
  middleware: 'dashboard.applicationTopologyGroupMiddleware',
  cache: 'dashboard.applicationTopologyGroupCache',
  message_queue: 'dashboard.applicationTopologyGroupMessageQueue',
  hardware: 'dashboard.applicationTopologyGroupHardware',
  rack_room: 'dashboard.applicationTopologyGroupRackRoom',
  other: 'dashboard.applicationTopologyGroupOther',
};

/** 方案 B：节点底色压暗，告警仍染在边框和底色上。 */
const NODE_PALETTE = {
  background: '#18344E',
  border: '#45617E',
  title: '#E8F0F7',
  meta: '#91A6B9',
  selected: '#38BDF8',
} as const;

const toneSurfaceStyle = (tone: ApplicationTopologyTone) => {
  if (tone === 'unknown') {
    return {
      borderColor: NODE_PALETTE.border,
      background: NODE_PALETTE.background,
    };
  }
  const color = applicationTopologyToneColor(tone);
  return {
    borderColor: `color-mix(in srgb, ${color} 72%, ${NODE_PALETTE.border})`,
    background: `color-mix(in srgb, ${color} 16%, ${NODE_PALETTE.background})`,
  };
};

export const applicationTopologySurfaceStyle = (usesScreenTheme: boolean) =>
  usesScreenTheme
    ? { background: 'transparent', overflow: 'hidden' as const }
    : relatedTopologyCanvasStyle(false);

interface ApplicationTopologyGraphViewProps {
  centerId: string;
  nodes: ApplicationTopologySourceNode[];
  links: ApplicationTopologySourceLink[];
  usesScreenTheme: boolean;
  shareMode: boolean;
  onRefresh?: () => void;
}

const ApplicationTopologyGraphView = ({
  centerId,
  nodes,
  links,
  usesScreenTheme,
  shareMode,
  onRefresh,
}: ApplicationTopologyGraphViewProps) => {
  const { t } = useTranslation();
  const markerId = useId().replace(/:/g, '');
  const viewportRef = useRef<HTMLDivElement>(null);
  const userAdjustedRef = useRef(false);
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const [laneWidth, setLaneWidth] = useState(720);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [hover, setHover] = useState<ApplicationTopologyHover>(null);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (next && next > 0) setLaneWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const layout = useMemo(
    () => buildApplicationTopologyLayout({ centerId, nodes, links, laneWidth }),
    [centerId, nodes, links, laneWidth],
  );
  const structureKey = `${centerId}|${layout.nodes.map((node) => node.id).join(',')}`;
  const structureRef = useRef(structureKey);
  if (structureRef.current !== structureKey) {
    structureRef.current = structureKey;
    userAdjustedRef.current = false;
  }
  const selected = layout.nodes.find((node) => node.id === selectedId) || null;
  const hoverFocus = useMemo(
    () => resolveApplicationTopologyHover(hover, layout.edges),
    [hover, layout.edges],
  );
  const activeEdges = layout.edges.filter((edge) => hoverFocus.edgeIds.has(edge.id));

  const fitView = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const nodeRight = layout.nodes.reduce(
      (right, node) => Math.max(right, node.x + APPLICATION_TOPOLOGY_NODE.width),
      0,
    );
    const nodeLeft = layout.nodes.reduce(
      (left, node) => Math.min(left, node.x),
      nodeRight,
    );
    const clusterPad = 8;
    const row = viewport.parentElement;
    const rowWidth = row?.clientWidth || viewport.clientWidth + LAYER_LABEL_RAIL_PX;
    const clusterX = Math.max(0, nodeLeft - clusterPad);
    const clusterWidth = Math.max(1, nodeRight - nodeLeft + clusterPad * 2);
    let rail = LAYER_LABEL_RAIL_PX;
    let next = { scale: 1, x: 0, y: 0 };
    for (let pass = 0; pass < 4; pass += 1) {
      next = fitApplicationTopologyLayers({
        viewportWidth: Math.max(1, rowWidth - rail),
        viewportHeight: viewport.clientHeight,
        clusterX,
        clusterWidth,
        layerHeight: layout.height,
        labelRailWidth: rail,
      });
      const solvedRail = applicationTopologyLabelRailWidth(next.scale);
      if (solvedRail === rail) break;
      rail = solvedRail;
    }
    setView((current) => {
      if (
        Math.abs(current.scale - next.scale) < 0.01
        && Math.abs(current.x - next.x) < 1
        && Math.abs(current.y - next.y) < 1
      ) {
        return current;
      }
      return { scale: next.scale, x: next.x, y: next.y };
    });
  }, [layout.height, layout.nodes]);

  useLayoutEffect(() => {
    if (userAdjustedRef.current) return;
    fitView();
  }, [fitView]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = viewport.getBoundingClientRect();
      userAdjustedRef.current = true;
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;
      setView((current) => zoomApplicationTopologyAt({
        scale: current.scale,
        x: current.x,
        y: current.y,
        pointerX,
        pointerY,
        nextScale: current.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12),
      }));
    };
    viewport.addEventListener('wheel', onWheel, { passive: false });
    return () => viewport.removeEventListener('wheel', onWheel);
  }, []);

  const zoomBy = (delta: number) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    userAdjustedRef.current = true;
    const pointerX = viewport.clientWidth / 2;
    const pointerY = viewport.clientHeight / 2;
    setView((current) => zoomApplicationTopologyAt({
      scale: current.scale,
      x: current.x,
      y: current.y,
      pointerX,
      pointerY,
      nextScale: current.scale + delta,
    }));
  };

  useEffect(() => {
    if (selectedId && !layout.nodes.some((node) => node.id === selectedId)) {
      setSelectedId(null);
    }
  }, [layout.nodes, selectedId]);

  const statusLabel = (node: ApplicationTopologyBandNode) => {
    if (node.tone === 'unknown') return t('dashboard.applicationTopologyUnmonitored');
    if (node.tone === 'normal') return t('dashboard.applicationTopologyNormal');
    if (node.tone === 'critical') return t('dashboard.applicationTopologyCritical');
    if (node.tone === 'error') return t('dashboard.applicationTopologyError');
    return t('dashboard.applicationTopologyWarning');
  };

  const chromeScale = applicationTopologyChromeScale(view.scale);
  const labelRail = applicationTopologyLabelRailWidth(view.scale);
  const layerFont = APPLICATION_TOPOLOGY_LAYER_LABEL_FONT * chromeScale;
  const legendFont = APPLICATION_TOPOLOGY_LEGEND_FONT;

  return (
    <div
      className="group relative flex h-full min-h-[280px] min-w-0 flex-col"
      style={applicationTopologySurfaceStyle(usesScreenTheme)}
    >
      <div
        className={`z-[1] flex flex-wrap items-center gap-3 py-2 pr-3 text-(--color-text-2) ${
          usesScreenTheme ? 'bg-transparent' : 'border-b border-(--color-border-1) bg-(--color-bg)/90'
        }`}
        style={{
          fontSize: legendFont,
          paddingLeft: Math.max(20, labelRail - 8 - layerFont * 5 + 16),
        }}
      >
        <Legend tone="critical" label={t('dashboard.applicationTopologyCritical')} scale={1} />
        <Legend tone="warning" label={t('dashboard.applicationTopologyWarning')} scale={1} />
        <Legend tone="normal" label={t('dashboard.applicationTopologyNormal')} scale={1} />
        <Legend tone="unknown" label={t('dashboard.applicationTopologyUnmonitored')} scale={1} />
      </div>
      <div className="pointer-events-none absolute top-2.5 right-2.5 z-20 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 focus-within:pointer-events-auto focus-within:opacity-100">
        <div className="pointer-events-auto flex items-center gap-1 rounded-lg border border-(--color-border-2) bg-[color-mix(in_srgb,var(--color-bg-1)_92%,transparent)] p-1 shadow-sm">
          <Tooltip title={t('dashboard.networkTopoZoomOut')}>
            <Button
              size="small"
              type="text"
              aria-label={t('dashboard.networkTopoZoomOut')}
              icon={<ZoomOutOutlined />}
              onClick={() => zoomBy(-APPLICATION_TOPOLOGY_SCALE.step)}
            />
          </Tooltip>
          <Tooltip title={t('dashboard.networkTopoZoomIn')}>
            <Button
              size="small"
              type="text"
              aria-label={t('dashboard.networkTopoZoomIn')}
              icon={<ZoomInOutlined />}
              onClick={() => zoomBy(APPLICATION_TOPOLOGY_SCALE.step)}
            />
          </Tooltip>
          <Tooltip title={t('topology.fitView')}>
            <Button
              size="small"
              type="text"
              aria-label={t('topology.fitView')}
              icon={<FullscreenOutlined />}
              onClick={() => {
                userAdjustedRef.current = true;
                fitView();
              }}
            />
          </Tooltip>
          {onRefresh ? (
            <Tooltip title={t('common.refresh')}>
              <Button
                size="small"
                type="text"
                aria-label={t('common.refresh')}
                icon={<ReloadOutlined />}
                onClick={onRefresh}
              />
            </Tooltip>
          ) : null}
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
      <div className="relative shrink-0 overflow-hidden" style={{ width: labelRail }}>
        {layout.bands.map((band) => (
          <div
            key={band.key}
            className="absolute right-2 left-1 text-right font-semibold whitespace-nowrap text-(--color-text-2)"
            style={{
              top: view.y + (band.top + band.height / 2) * view.scale,
              fontSize: layerFont,
              transform: 'translateY(-50%)',
            }}
          >
            {t(LAYER_LABEL_KEY[band.key])}
          </div>
        ))}
      </div>
      <div
        ref={viewportRef}
        className="relative min-h-0 min-w-0 flex-1 cursor-grab overflow-hidden active:cursor-grabbing"
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest('button')) return;
          dragRef.current = {
            x: event.clientX,
            y: event.clientY,
            ox: view.x,
            oy: view.y,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (!drag) return;
          userAdjustedRef.current = true;
          setView((current) => ({
            ...current,
            x: drag.ox + event.clientX - drag.x,
            y: drag.oy + event.clientY - drag.y,
          }));
        }}
        onPointerUp={() => {
          dragRef.current = null;
        }}
      >
        {layout.bands.slice(0, -1).map((band) => (
          <div
            key={band.key}
            className="pointer-events-none absolute right-0 left-0 z-0"
            style={{
              top: view.y + (band.top + band.height + APPLICATION_TOPOLOGY_LAYOUT.layerGap / 2) * view.scale,
              borderTop: '1px dashed color-mix(in srgb, var(--color-text-3) 18%, transparent)',
            }}
          />
        ))}
        <div
          className="relative z-[1] origin-top-left"
          style={{
            width: layout.width,
            height: layout.height,
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          }}
        >
          <svg
            className="pointer-events-none absolute inset-0 z-0 overflow-visible"
            width={layout.width}
            height={layout.height}
          >
            <EdgeMarkers markerId={markerId} color="var(--color-text-3)" />
            <LineGapMask markerId={markerId} edges={layout.edges} width={layout.width} height={layout.height} />
            {layout.edges.map((edge) => {
              const active = hoverFocus.edgeIds.has(edge.id);
              const path = edgePath(edge);
              return (
                <g key={edge.id}>
                  <path
                    d={path}
                    fill="none"
                    stroke="transparent"
                    strokeWidth={14}
                    style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                    onMouseEnter={() => setHover({ kind: 'edge', id: edge.id })}
                    onMouseLeave={() => setHover((current) => (
                      current?.kind === 'edge' && current.id === edge.id ? null : current
                    ))}
                  />
                  <path
                    d={path}
                    fill="none"
                    stroke="color-mix(in srgb, var(--color-text-3) 65%, var(--color-border-3))"
                    strokeWidth={1.35}
                    strokeOpacity={active ? 0.2 : 0.78}
                    mask={`url(#${markerId}-line-gap)`}
                    markerEnd={edge.markerEnd ? `url(#${markerId}-end)` : undefined}
                    markerStart={edge.markerStart ? `url(#${markerId}-start)` : undefined}
                  />
                </g>
              );
            })}
            {layout.edges.map((edge) => {
              const mid = polylineMidpoint(edge.points);
              if (!edge.label || !mid || hoverFocus.edgeIds.has(edge.id)) return null;
              return <EdgeLabel key={`label-${edge.id}`} edge={edge} mid={mid} active={false} />;
            })}
          </svg>
          {activeEdges.length ? (
            <svg
              className="pointer-events-none absolute inset-0 z-[2] overflow-visible"
              width={layout.width}
              height={layout.height}
              aria-hidden
            >
              <EdgeMarkers markerId={`${markerId}-active`} color={HOVER_COLOR} />
              {activeEdges.map((edge) => (
                <path
                  key={edge.id}
                  d={edgePath(edge)}
                  fill="none"
                  stroke={HOVER_COLOR}
                  strokeWidth={2.1}
                  strokeOpacity={0.88}
                  mask={`url(#${markerId}-line-gap)`}
                  markerEnd={edge.markerEnd ? `url(#${markerId}-active-end)` : undefined}
                  markerStart={edge.markerStart ? `url(#${markerId}-active-start)` : undefined}
                />
              ))}
            </svg>
          ) : null}
          {layout.nodes.map((node) => {
            const pressed = node.id === selectedId;
            const highlighted = hoverFocus.nodeIds.has(node.id);
            return (
              <button
                key={node.id}
                type="button"
                aria-pressed={pressed}
                className="absolute flex cursor-pointer rounded-md border-2 text-left shadow-sm transition-[border-color,box-shadow] hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                style={{
                  left: node.x,
                  top: node.y,
                  width: APPLICATION_TOPOLOGY_NODE.width,
                  height: APPLICATION_TOPOLOGY_NODE.height,
                  zIndex: highlighted ? 3 : 1,
                  outline: highlighted ? `2px solid ${HOVER_COLOR}` : undefined,
                  outlineColor: NODE_PALETTE.selected,
                  outlineOffset: highlighted ? 2 : undefined,
                  boxShadow: [
                    pressed ? `0 0 0 2px ${NODE_PALETTE.selected}` : '',
                    highlighted ? '0 4px 8px var(--color-portal-card-shadow)' : '',
                  ].filter(Boolean).join(', ') || undefined,
                  ...toneSurfaceStyle(node.tone),
                }}
                onMouseEnter={() => setHover({ kind: 'node', id: node.id })}
                onMouseLeave={() => setHover((current) => (
                  current?.kind === 'node' && current.id === node.id ? null : current
                ))}
                onClick={() => setSelectedId(node.id)}
              >
                <span className="flex w-10 shrink-0 items-center justify-center">
                  <img
                    src={getIconUrl({ icn: '', model_id: node.modelId })}
                    alt=""
                    className="h-[34px] w-[34px]"
                  />
                </span>
                <span className="flex min-w-0 flex-1 flex-col justify-center pr-3 pl-1">
                  <span
                    className="block truncate text-base font-semibold"
                    style={{ color: NODE_PALETTE.title }}
                  >
                    {node.name}
                  </span>
                  <span
                    className="block truncate text-sm"
                    style={{ color: NODE_PALETTE.meta }}
                  >
                    {node.modelId} · {t(CATEGORY_LABEL_KEY[node.category] || CATEGORY_LABEL_KEY.other)}
                  </span>
                </span>
                {node.badge ? (
                  <span
                    className="absolute -top-2 -right-2 min-w-5 rounded-full px-1 text-center text-[10px] leading-4 text-white"
                    style={{ backgroundColor: applicationTopologyToneColor(node.tone) }}
                  >
                    {node.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
          {activeEdges.length ? (
            <svg
              className="pointer-events-none absolute inset-0 z-[4] overflow-visible"
              width={layout.width}
              height={layout.height}
              aria-hidden
            >
              {activeEdges.map((edge) => {
                const mid = polylineMidpoint(edge.points);
                if (!edge.label || !mid) return null;
                return <EdgeLabel key={edge.id} edge={edge} mid={mid} active />;
              })}
            </svg>
          ) : null}
        </div>
      </div>
      </div>
      {selected ? (
        <ApplicationTopologyDetailPanel
          node={selected}
          statusLabel={statusLabel(selected)}
          shareMode={shareMode}
          onClose={() => setSelectedId(null)}
        />
      ) : null}
    </div>
  );
};

const edgePath = (edge: ApplicationTopologyEdge) =>
  edge.points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`).join(' ');

const EdgeMarkers = ({ markerId, color }: { markerId: string; color: string }) => (
  <defs>
    <marker
      id={`${markerId}-end`}
      markerWidth="6"
      markerHeight="6"
      refX="5"
      refY="3"
      orient="auto"
    >
      <path d="M0,0 L6,3 L0,6 Z" fill={color} />
    </marker>
    <marker
      id={`${markerId}-start`}
      markerWidth="6"
      markerHeight="6"
      refX="1"
      refY="3"
      orient="auto-start-reverse"
    >
      <path d="M0,0 L6,3 L0,6 Z" fill={color} />
    </marker>
  </defs>
);

const RELATION_LABEL_FONT = 14;
const RELATION_LABEL_HOVER_FONT = 16;

const relationLabelGap = (
  label: string,
  mid: { x: number; y: number },
  fontSize: number,
) => {
  const lines = label.split('\n');
  const longest = lines.reduce((max, line) => Math.max(max, line.length), 0);
  const width = Math.min(240, Math.max(24, longest * fontSize * 0.62 + 10));
  const height = lines.length * (fontSize + 3) + 2;
  return {
    x: mid.x - width / 2,
    y: mid.y - height / 2,
    width,
    height,
  };
};

const LineGapMask = ({
  markerId,
  edges,
  width,
  height,
}: {
  markerId: string;
  edges: ApplicationTopologyEdge[];
  width: number;
  height: number;
}) => (
  <mask
    id={`${markerId}-line-gap`}
    maskUnits="userSpaceOnUse"
    x={0}
    y={0}
    width={width}
    height={height}
  >
    <rect x={0} y={0} width={width} height={height} fill="#fff" />
    {edges.map((edge) => {
      const mid = edge.label ? polylineMidpoint(edge.points) : null;
      if (!edge.label || !mid) return null;
      const gap = relationLabelGap(edge.label, mid, RELATION_LABEL_FONT);
      return <rect key={edge.id} {...gap} fill="#000" />;
    })}
  </mask>
);

const EdgeLabel = ({
  edge,
  mid,
  active,
}: {
  edge: ApplicationTopologyEdge;
  mid: { x: number; y: number };
  active: boolean;
}) => {
  if (!edge.label) return null;
  if (!active) {
    return (
      <text
        x={mid.x}
        y={mid.y}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={RELATION_LABEL_FONT}
        fill="var(--color-text-2)"
      >
        {edge.label}
      </text>
    );
  }
  const width = Math.min(220, Math.max(56, edge.label.length * 9.2 + 22));
  const height = 26;
  return (
    <g>
      <rect
        x={mid.x - width / 2}
        y={mid.y - height / 2}
        width={width}
        height={height}
        rx={5}
        fill="color-mix(in srgb, var(--color-primary) 78%, white)"
      />
      <text
        x={mid.x}
        y={mid.y}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={RELATION_LABEL_HOVER_FONT}
        fontWeight={700}
        fill="var(--color-primary-foreground)"
      >
        {edge.label}
      </text>
    </g>
  );
};

const polylineMidpoint = (points: Array<{ x: number; y: number }>) => {
  if (!points.length) return null;
  let total = 0;
  const lengths = points.slice(1).map((point, index) => {
    const length = Math.hypot(point.x - points[index].x, point.y - points[index].y);
    total += length;
    return length;
  });
  let remain = total / 2;
  for (let index = 1; index < points.length; index += 1) {
    const length = lengths[index - 1];
    if (length >= remain) {
      const ratio = length === 0 ? 0 : remain / length;
      return {
        x: points[index - 1].x + (points[index].x - points[index - 1].x) * ratio,
        y: points[index - 1].y + (points[index].y - points[index - 1].y) * ratio,
      };
    }
    remain -= length;
  }
  return points[points.length - 1];
};

const Legend = ({
  tone,
  label,
  scale,
}: {
  tone: ApplicationTopologyTone;
  label: string;
  scale: number;
}) => (
  <span className="inline-flex items-center gap-1.5">
    <span
      className="inline-block rounded-sm border-2"
      style={{
        ...toneSurfaceStyle(tone),
        width: 10 * scale,
        height: 10 * scale,
      }}
    />
    {label}
  </span>
);

export default ApplicationTopologyGraphView;
