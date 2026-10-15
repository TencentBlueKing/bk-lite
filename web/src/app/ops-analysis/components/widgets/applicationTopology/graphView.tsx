'use client';

import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button, Tooltip } from 'antd';
import {
  ApiOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  ClusterOutlined,
  FullscreenOutlined,
  HddOutlined,
  ReloadOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getIconUrl } from '@/app/cmdb/utils/modelIcon';
import { relatedTopologyCanvasStyle } from '@/app/ops-analysis/components/widgets/relatedTopology/visual';
import {
  APPLICATION_TOPOLOGY_NODE,
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
  APPLICATION_TOPOLOGY_LABEL_GAP,
  APPLICATION_TOPOLOGY_LEGEND_FONT,
  APPLICATION_TOPOLOGY_NODE_TITLE_FONT,
  APPLICATION_TOPOLOGY_SCALE,
  applicationTopologyChromeScale,
  applicationTopologyLabelRailWidth,
  fitApplicationTopologyLayers,
  resolveApplicationTopologyLaneWidth,
  resolveApplicationTopologyViewportBox,
  zoomApplicationTopologyAt,
} from './viewport';

const LAYER_LABEL_KEY: Record<ApplicationTopologyBandNode['layer'], string> = {
  root: 'dashboard.applicationTopologyLayerSystem',
  service: 'dashboard.applicationTopologyLayerService',
  host: 'dashboard.applicationTopologyLayerHost',
  appService: 'dashboard.applicationTopologyLayerAppService',
  infrastructure: 'dashboard.applicationTopologyLayerInfrastructure',
};

const LAYER_COUNT_KEY: Record<ApplicationTopologyBandNode['layer'], string> = {
  root: 'dashboard.applicationTopologyLayerCountSystem',
  service: 'dashboard.applicationTopologyLayerCountService',
  host: 'dashboard.applicationTopologyLayerCountHost',
  appService: 'dashboard.applicationTopologyLayerCountAppService',
  infrastructure: 'dashboard.applicationTopologyLayerCountInfrastructure',
};

const LAYER_ICON: Record<ApplicationTopologyBandNode['layer'], typeof AppstoreOutlined> = {
  root: AppstoreOutlined,
  service: ClusterOutlined,
  host: CloudServerOutlined,
  appService: ApiOutlined,
  infrastructure: HddOutlined,
};

const HOVER_COLOR = 'color-mix(in srgb, var(--color-primary) 72%, var(--color-bg))';
/** 与 CMDB 应用拓扑的 rounded connector 相同，只圆角、不改走线。 */
const EDGE_CORNER_RADIUS = 10;
/**
 * 大屏把 --color-text-3 / --color-border-3 重写成半透明色。
 * 沿用 CMDB 的 color-mix 会在深色底上发虚，这里用实色。
 */
const SCREEN_EDGE_STROKE = '#A9C3D6';
/** 悬停时未点亮的节点、线和关系文字只略微退后，仍能辨认。 */
const HOVER_MUTE_OPACITY = 0.55;

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

/** 未告警节点保持这套深色；告警才换边框和底色。 */
const NODE_PALETTE = {
  background: '#18344E',
  border: '#45617E',
  title: '#E8F0F7',
  meta: '#91A6B9',
  selected: '#38BDF8',
} as const;

/** 图例和节点角标。正常、告警、未接入都用实心圆，不用整块染色。 */
const STATUS_MARK: Record<ApplicationTopologyTone, string> = {
  normal: '#22C55E',
  warning: '#F59E0B',
  error: '#D97007',
  critical: '#EF4444',
  unknown: '#94A3B8',
};

const ALERT_SURFACE: Record<'warning' | 'error' | 'critical', { borderColor: string; background: string }> = {
  warning: { borderColor: '#A66A2E', background: '#302B29' },
  // 图里没有错误档，沿用同一套暗底加色边，角标仍用监控的错误色。
  error: { borderColor: '#A56A32', background: '#32281F' },
  critical: { borderColor: '#B84B57', background: '#33252F' },
};

const toneSurfaceStyle = (tone: ApplicationTopologyTone) => {
  if (tone === 'normal') {
    return {
      borderColor: NODE_PALETTE.border,
      background: NODE_PALETTE.background,
    };
  }
  if (tone === 'unknown') {
    return {
      borderColor: '#485A6C',
      background: NODE_PALETTE.background,
    };
  }
  return ALERT_SURFACE[tone];
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
  screenScaleX?: number;
  screenScaleY?: number;
  onRefresh?: () => void;
}

const ApplicationTopologyGraphView = ({
  centerId,
  nodes,
  links,
  usesScreenTheme,
  shareMode,
  screenScaleX,
  screenScaleY,
  onRefresh,
}: ApplicationTopologyGraphViewProps) => {
  const { t } = useTranslation();
  const markerId = useId().replace(/:/g, '');
  const viewportRef = useRef<HTMLDivElement>(null);
  const userAdjustedRef = useRef(false);
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const [viewport, setViewport] = useState(() => resolveApplicationTopologyViewportBox({
    contentWidth: 720,
    contentHeight: 480,
    visualWidth: 720,
    visualHeight: 480,
  }));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [hover, setHover] = useState<ApplicationTopologyHover>(null);

  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const measure = () => {
      const contentWidth = element.clientWidth;
      const contentHeight = element.clientHeight;
      if (contentWidth <= 0 || contentHeight <= 0) return;
      const rect = element.getBoundingClientRect();
      const next = resolveApplicationTopologyViewportBox({
        contentWidth,
        contentHeight,
        visualWidth: rect.width,
        visualHeight: rect.height,
      });
      setViewport((current) => {
        if (
          Math.abs(current.visualWidth - next.visualWidth) < 1
          && Math.abs(current.visualHeight - next.visualHeight) < 1
          && Math.abs(current.contentScaleX - next.contentScaleX) < 0.001
          && Math.abs(current.contentScaleY - next.contentScaleY) < 0.001
        ) {
          return current;
        }
        userAdjustedRef.current = false;
        return next;
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [screenScaleX, screenScaleY]);

  const layout = useMemo(() => {
    const laneWidth = resolveApplicationTopologyLaneWidth({
      viewportWidth: viewport.visualWidth,
      viewportHeight: viewport.visualHeight,
      labelRailWidth: applicationTopologyLabelRailWidth(1),
      measure: (nextLane) => {
        const measured = buildApplicationTopologyLayout({
          centerId,
          nodes,
          links,
          laneWidth: nextLane,
        });
        return { width: measured.width, height: measured.height };
      },
    });
    return buildApplicationTopologyLayout({ centerId, nodes, links, laneWidth });
  }, [centerId, links, nodes, viewport.visualHeight, viewport.visualWidth]);
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
  const muteRest = hover !== null;

  const fitView = useCallback(() => {
    let rail = applicationTopologyLabelRailWidth(1);
    let next = { scale: 1, x: 0, y: 0 };
    for (let pass = 0; pass < 4; pass += 1) {
      next = fitApplicationTopologyLayers({
        viewportWidth: viewport.visualWidth,
        viewportHeight: viewport.visualHeight,
        clusterX: 0,
        clusterWidth: layout.width,
        layerHeight: layout.height,
        labelRailWidth: rail,
        labelGap: APPLICATION_TOPOLOGY_LABEL_GAP,
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
  }, [layout.height, layout.width, viewport.visualHeight, viewport.visualWidth]);

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
    userAdjustedRef.current = true;
    const pointerX = viewport.visualWidth / 2;
    const pointerY = viewport.visualHeight / 2;
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
  const nodeTitleSize = APPLICATION_TOPOLOGY_NODE_TITLE_FONT * view.scale;
  const layerTitleSize = nodeTitleSize;
  const layerCountSize = 14 * chromeScale;
  const layerIconBox = 28 * chromeScale;
  const layerCardHeight = Math.max(
    36,
    layerIconBox + 12,
    layerTitleSize * 1.2 + layerCountSize * 1.3 + 4 * chromeScale + 12,
  );
  const labelLeft = view.x - labelRail - APPLICATION_TOPOLOGY_LABEL_GAP;
  const layerCounts = useMemo(() => {
    const counts: Record<ApplicationTopologyBandNode['layer'], number> = {
      root: 0,
      service: 0,
      host: 0,
      appService: 0,
      infrastructure: 0,
    };
    layout.nodes.forEach((node) => {
      counts[node.layer] += 1;
    });
    return counts;
  }, [layout.nodes]);

  return (
    <div
      className="group relative flex h-full min-h-[280px] min-w-0 flex-col overflow-hidden"
      style={applicationTopologySurfaceStyle(usesScreenTheme)}
    >
      <div
        className={`z-[1] flex flex-wrap items-center gap-3 py-2 pr-3 text-(--color-text-2) ${
          usesScreenTheme ? 'bg-transparent' : 'border-b border-(--color-border-1) bg-(--color-bg)/90'
        }`}
        style={{
          fontSize: APPLICATION_TOPOLOGY_LEGEND_FONT,
          paddingLeft: Math.max(12, labelLeft * viewport.contentScaleX),
        }}
      >
        <Legend tone="critical" label={t('dashboard.applicationTopologyCritical')} />
        <Legend tone="warning" label={t('dashboard.applicationTopologyWarning')} />
        <Legend tone="normal" label={t('dashboard.applicationTopologyNormal')} />
        <Legend tone="unknown" label={t('dashboard.applicationTopologyUnmonitored')} />
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
      <div
        ref={viewportRef}
        className="relative min-h-0 flex-1 overflow-hidden"
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
      <div
        className="absolute top-0 left-0 overflow-hidden"
        style={{
          width: viewport.visualWidth,
          height: viewport.visualHeight,
          transform: `scale(${viewport.contentScaleX}, ${viewport.contentScaleY})`,
          transformOrigin: 'top left',
        }}
      >
      <div className="relative h-full w-full">
      <div
        className="pointer-events-none absolute top-0 bottom-0 z-[3]"
        style={{ left: labelLeft, width: labelRail }}
      >
        {layout.bands.map((band) => {
          const Icon = LAYER_ICON[band.key];
          const cardHeight = layerCardHeight;
          return (
            <div
              key={band.key}
              className="pointer-events-none absolute right-1.5 left-1.5 flex items-center gap-2 overflow-hidden rounded-lg border border-(--color-border-2) bg-[color-mix(in_srgb,var(--color-bg-1)_78%,transparent)] px-2"
              style={{
                top: view.y + (band.top + band.height / 2) * view.scale - cardHeight / 2,
                height: cardHeight,
              }}
            >
              <span
                className="flex shrink-0 items-center justify-center rounded-md bg-[color-mix(in_srgb,var(--color-primary)_18%,transparent)] text-(--color-primary)"
                style={{ width: layerIconBox, height: layerIconBox }}
              >
                <Icon style={{ fontSize: 15 * chromeScale }} />
              </span>
              <span className="flex min-w-0 flex-col" style={{ gap: 4 * chromeScale }}>
                <span
                  className="block truncate font-semibold text-(--color-text-1)"
                  style={{ fontSize: layerTitleSize, lineHeight: 1.2 }}
                >
                  {t(LAYER_LABEL_KEY[band.key])}
                </span>
                <span
                  className="block truncate text-(--color-text-3)"
                  style={{ fontSize: layerCountSize, lineHeight: 1.3 }}
                >
                  {t(LAYER_COUNT_KEY[band.key], undefined, { count: layerCounts[band.key] })}
                </span>
              </span>
            </div>
          );
        })}
      </div>
      <div className="relative h-full w-full cursor-grab overflow-hidden active:cursor-grabbing">
        <div
          className="absolute z-[1]"
          style={{ left: view.x, top: view.y }}
        >
        <div
          className="origin-top-left overflow-hidden"
          style={{
            width: layout.width,
            height: layout.height,
            zoom: view.scale,
          }}
        >
          {layout.bands.map((band) => (
            <div
              key={band.key}
              className="pointer-events-none absolute rounded-xl"
              style={{
                left: 0,
                width: layout.width,
                top: band.top,
                height: band.height,
                background: 'rgba(16, 40, 62, 0.62)',
                border: '1px solid rgba(90, 124, 156, 0.24)',
              }}
            />
          ))}
          <svg
            className="pointer-events-none absolute inset-0 z-0 overflow-visible"
            width={layout.width}
            height={layout.height}
          >
            <EdgeMarkers
              markerId={markerId}
              color={usesScreenTheme ? SCREEN_EDGE_STROKE : 'var(--color-text-3)'}
            />
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
                    onMouseLeave={(event) => {
                      if (event.relatedTarget == null) return;
                      setHover((current) => (
                        current?.kind === 'edge' && current.id === edge.id ? null : current
                      ));
                    }}
                  />
                  <path
                    d={path}
                    fill="none"
                    stroke={usesScreenTheme
                      ? SCREEN_EDGE_STROKE
                      : 'color-mix(in srgb, var(--color-text-3) 65%, var(--color-border-3))'}
                    strokeWidth={1.35}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeOpacity={active ? 0.2 : (usesScreenTheme ? 1 : 0.78)}
                    opacity={muteRest && !active ? HOVER_MUTE_OPACITY : 1}
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
              return (
                <EdgeLabel
                  key={`label-${edge.id}`}
                  edge={edge}
                  mid={mid}
                  active={false}
                  muted={muteRest}
                />
              );
            })}
          </svg>
          <svg
            className="pointer-events-none absolute inset-0 z-[2] overflow-visible"
            style={{ pointerEvents: 'none' }}
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
                markerEnd={edge.markerEnd ? `url(#${markerId}-active-end)` : undefined}
                markerStart={edge.markerStart ? `url(#${markerId}-active-start)` : undefined}
              />
            ))}
            {activeEdges.map((edge) => {
              const mid = polylineMidpoint(edge.points);
              if (!edge.label || !mid) return null;
              return <EdgeLabel key={`active-${edge.id}`} edge={edge} mid={mid} active />;
            })}
          </svg>
          {layout.nodes.map((node) => {
            const pressed = node.id === selectedId;
            const highlighted = hoverFocus.nodeIds.has(node.id);
            const muted = muteRest && !highlighted;
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
                  opacity: muted ? HOVER_MUTE_OPACITY : 1,
                  outlineWidth: highlighted ? 2 : undefined,
                  outlineStyle: highlighted ? 'solid' : undefined,
                  outlineColor: highlighted ? HOVER_COLOR : NODE_PALETTE.selected,
                  outlineOffset: highlighted ? 2 : undefined,
                  boxShadow: [
                    pressed ? `0 0 0 2px ${NODE_PALETTE.selected}` : '',
                    highlighted ? '0 4px 8px var(--color-portal-card-shadow)' : '',
                  ].filter(Boolean).join(', ') || undefined,
                  ...toneSurfaceStyle(node.tone),
                }}
                onMouseEnter={() => setHover({ kind: 'node', id: node.id })}
                onMouseLeave={(event) => {
                  if (event.relatedTarget == null) return;
                  setHover((current) => (
                    current?.kind === 'node' && current.id === node.id ? null : current
                  ));
                }}
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
                <StatusMark tone={node.tone} badge={node.badge} />
              </button>
            );
          })}
        </div>
        </div>
      </div>
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
  roundedPolyline(edge.points, EDGE_CORNER_RADIUS);

/** 两点保持直线；折点按给定半径倒角，对应 CMDB 的 rounded connector。 */
const roundedPolyline = (
  points: Array<{ x: number; y: number }>,
  radius: number,
) => {
  if (points.length < 2) return '';
  const [first] = points;
  let path = `M${first.x} ${first.y}`;
  if (points.length === 2) {
    const last = points[1];
    return `${path} L${last.x} ${last.y}`;
  }
  for (let index = 1; index < points.length - 1; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const next = points[index + 1];
    const inLength = Math.hypot(current.x - previous.x, current.y - previous.y);
    const outLength = Math.hypot(next.x - current.x, next.y - current.y);
    const corner = Math.min(radius, inLength / 2, outLength / 2);
    if (inLength < 1 || outLength < 1 || corner < 0.5) {
      path += ` L${current.x} ${current.y}`;
      continue;
    }
    const inX = current.x - ((current.x - previous.x) / inLength) * corner;
    const inY = current.y - ((current.y - previous.y) / inLength) * corner;
    const outX = current.x + ((next.x - current.x) / outLength) * corner;
    const outY = current.y + ((next.y - current.y) / outLength) * corner;
    path += ` L${inX} ${inY} Q${current.x} ${current.y} ${outX} ${outY}`;
  }
  const last = points[points.length - 1];
  return `${path} L${last.x} ${last.y}`;
};

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
  muted = false,
}: {
  edge: ApplicationTopologyEdge;
  mid: { x: number; y: number };
  active: boolean;
  muted?: boolean;
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
        fillOpacity={muted ? HOVER_MUTE_OPACITY : 1}
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

const StatusMark = ({
  tone,
  badge,
}: {
  tone: ApplicationTopologyTone;
  badge: string | null;
}) => {
  if (badge) {
    return (
      <span
        className="absolute -top-2 -right-2 min-w-5 rounded-full px-1 text-center text-[10px] leading-4 text-white"
        style={{ backgroundColor: STATUS_MARK[tone] }}
      >
        {badge}
      </span>
    );
  }
  if (tone !== 'normal') return null;
  return (
    <span
      className="pointer-events-none absolute top-1.5 right-1.5 h-2 w-2 rounded-full"
      style={{ backgroundColor: STATUS_MARK.normal }}
      aria-hidden
    />
  );
};

const Legend = ({
  tone,
  label,
}: {
  tone: ApplicationTopologyTone;
  label: string;
}) => (
  <span className="inline-flex items-center gap-1.5">
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ backgroundColor: STATUS_MARK[tone] }}
    />
    {label}
  </span>
);

export default ApplicationTopologyGraphView;
