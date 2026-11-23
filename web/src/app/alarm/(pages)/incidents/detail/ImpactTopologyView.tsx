'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, Pagination, Spin, Table } from 'antd';
import { CloseOutlined, FullscreenExitOutlined, FullscreenOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { buildAlarmDetailUrl } from '@/app/alarm/(pages)/alarms/alarmDetailLink';
import type { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import type { LevelItem } from '@/app/alarm/types';
import {
  IMPACT_NODE_HEIGHT,
  IMPACT_NODE_WIDTH,
  buildImpactGraph,
  type ImpactCopy,
  type ImpactGraphNode,
  type ImpactTopologyPayload,
} from './impactTopology';

export interface ImpactAlertPage {
  count: number;
  page: number;
  page_size: number;
  items: Array<{
    id: number;
    alert_id?: string;
    title?: string;
    level?: string;
    status?: string;
    in_incident?: boolean;
  }>;
}

const MIN_ZOOM = 0.2;
const MAX_ZOOM = 2.5;

interface ImpactTopologyViewProps {
  alerts: AlarmTableDataItem[];
  payload: ImpactTopologyPayload | null;
  loading?: boolean;
  levels?: LevelItem[];
  levelColors?: Record<string, string>;
  loadAlerts?: (instUuid: string, page: number) => Promise<ImpactAlertPage>;
}

const PROTOTYPE_BRIDGE = {
  border: '#7be188',
  background: '#f0fff1',
  caption: '#00b42a',
};

const PROTOTYPE_UNBOUND = {
  border: '#c9cdd4',
  background: '#f2f3f5',
  caption: '#86909c',
  title: '#4e5969',
};

const ImpactTopologyView: React.FC<ImpactTopologyViewProps> = ({
  alerts,
  payload,
  loading = false,
  levels = [],
  levelColors = {},
  loadAlerts,
}) => {
  const { t } = useTranslation();
  const copy = useMemo<ImpactCopy>(() => ({
    bridge: t('incidents.impactBridge', '桥接'),
    unbound: t('incidents.impactUnbound', '未绑定 CMDB'),
    alertCount: (count) => t('incidents.impactAlertCount', '{count} 条告警', { count }),
    notPurchased: t('incidents.impactNotPurchased', '未购买 CMDB，无法按配置关系展示影响拓扑'),
    unavailable: t('incidents.impactUnavailable', '配置关系暂时查不到'),
    truncated: t('incidents.impactTruncatedHint', '关系未展开'),
    unboundHint: t('incidents.impactUnboundHint', '这些告警没有绑定 CMDB 对象'),
    noAlert: t('incidents.impactNoAlert', '无告警'),
    alertUnknown: t('incidents.impactAlertUnknown', '告警情况暂时查不到'),
    outside: (count) => t('incidents.impactOutside', '另有 {count} 条未入本事故', { count }),
    quietOmitted: (count) => t('incidents.impactQuietOmitted', '还有 {count} 个关联对象当前无告警未画入，入画请点击。', { count }),
    relatedTruncated: t('incidents.impactRelatedTruncated', '关联对象过多，只展示一部分'),
    atLeast: (count) => t('incidents.impactAtLeast', '至少 {count} 条', { count }),
  }), [t]);
  const [drawOmitted, setDrawOmitted] = useState(false);
  const model = useMemo(
    () => buildImpactGraph(alerts, payload, levels, levelColors, copy, drawOmitted),
    [alerts, payload, levels, levelColors, copy, drawOmitted],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [alertPage, setAlertPage] = useState(1);
  const [alertItems, setAlertItems] = useState<ImpactAlertPage['items']>([]);
  const [alertTotal, setAlertTotal] = useState(0);
  const [alertListError, setAlertListError] = useState(false);
  const [alertListLoading, setAlertListLoading] = useState(false);
  const loadAlertsRef = useRef(loadAlerts);
  loadAlertsRef.current = loadAlerts;
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const stopCanvasTrackRef = useRef<(() => void) | null>(null);
  const stopNodeTrackRef = useRef<(() => void) | null>(null);
  const viewRef = useRef({ x: 0, y: 0, k: 1 });
  viewRef.current = { x: pan.x, y: pan.y, k: zoom };
  const dragRef = useRef({ active: false, moved: false, startX: 0, startY: 0, originX: 0, originY: 0 });
  const [nodeOffsets, setNodeOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const nodeDragRef = useRef({
    active: false,
    moved: false,
    id: '',
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  });
  const suppressClickRef = useRef(false);
  const selected = model.nodes.find((node) => node.id === selectedId) || null;
  const layoutKey = model.nodes.map((node) => `${node.id}:${node.x}:${node.y}`).join('|');
  const placed = useMemo(() => placeNodes(model.nodes, nodeOffsets, model.width, model.height), [
    model.nodes,
    model.width,
    model.height,
    nodeOffsets,
  ]);
  useEffect(() => {
    setDrawOmitted(false);
  }, [payload]);
  useEffect(() => {
    setNodeOffsets({});
  }, [layoutKey]);
  useEffect(() => {
    const canvas = canvasRef.current;
    const rect = canvas?.getBoundingClientRect();
    if (!rect || rect.width < 40 || rect.height < 40 || !model.width || !model.height) {
      setZoom(1);
      setPan({ x: 0, y: 0 });
      return;
    }
    const fitted = Math.max(
      MIN_ZOOM,
      Math.min(1, (rect.width - 32) / model.width, (rect.height - 32) / model.height),
    );
    setZoom(fitted);
    setPan({
      x: Math.max(16, (rect.width - model.width * fitted) / 2),
      y: Math.max(16, (rect.height - model.height * fitted) / 2),
    });
  }, [layoutKey, model.width, model.height, fullscreen]);
  useEffect(() => {
    const syncFullscreen = () => setFullscreen(document.fullscreenElement === shellRef.current);
    document.addEventListener('fullscreenchange', syncFullscreen);
    return () => document.removeEventListener('fullscreenchange', syncFullscreen);
  }, []);
  useEffect(() => () => {
    stopCanvasTrackRef.current?.();
    stopNodeTrackRef.current?.();
  }, []);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const originX = event.clientX - rect.left;
      const originY = event.clientY - rect.top;
      const current = viewRef.current;
      const next = clampZoom(current.k * (event.deltaY > 0 ? 0.9 : 1.1));
      const worldX = (originX - current.x) / current.k;
      const worldY = (originY - current.y) / current.k;
      setZoom(next);
      setPan({ x: originX - worldX * next, y: originY - worldY * next });
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [model.mode]);
  useEffect(() => {
    setAlertPage(1);
    setAlertItems([]);
    setAlertTotal(0);
    setAlertListError(false);
  }, [selectedId]);
  useEffect(() => {
    const load = loadAlertsRef.current;
    if (!selected || selected.kind === 'unbound' || !load) return undefined;
    let cancelled = false;
    setAlertListLoading(true);
    setAlertListError(false);
    load(selected.id, alertPage).then((body) => {
      if (cancelled) return;
      setAlertItems(body.items || []);
      setAlertTotal(Number(body.count || 0));
    }).catch(() => {
      if (cancelled) return;
      setAlertItems([]);
      setAlertListError(true);
    }).finally(() => {
      if (!cancelled) setAlertListLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [selected, alertPage]);

  const onCanvasPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('[data-kind],button')) return;
    stopCanvasTrackRef.current?.();
    const pointerId = event.pointerId;
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };
    const finish = (pointerEvent?: PointerEvent) => {
      if (pointerEvent && pointerEvent.pointerId !== pointerId) return;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      if (stopCanvasTrackRef.current === finish) stopCanvasTrackRef.current = null;
      if (!dragRef.current.active) return;
      dragRef.current.active = false;
      dragRef.current.moved = false;
      setPanning(false);
    };
    const move = (pointerEvent: PointerEvent) => {
      if (pointerEvent.pointerId !== pointerId) return;
      const drag = dragRef.current;
      if (!drag.active) return;
      if ((pointerEvent.buttons & 1) === 0) {
        finish(pointerEvent);
        return;
      }
      const dx = pointerEvent.clientX - drag.startX;
      const dy = pointerEvent.clientY - drag.startY;
      if (!drag.moved && Math.hypot(dx, dy) < 4) return;
      drag.moved = true;
      setPanning(true);
      setPan({ x: drag.originX + dx, y: drag.originY + dy });
    };
    stopCanvasTrackRef.current = () => finish();
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
  };

  const onNodePointerDown = (nodeId: string, event: React.PointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (event.button !== 0) return;
    stopNodeTrackRef.current?.();
    const pointerId = event.pointerId;
    const current = nodeOffsets[nodeId] || { x: 0, y: 0 };
    nodeDragRef.current = {
      active: true,
      moved: false,
      id: nodeId,
      startX: event.clientX,
      startY: event.clientY,
      originX: current.x,
      originY: current.y,
    };
    const finish = (pointerEvent?: PointerEvent) => {
      if (pointerEvent && pointerEvent.pointerId !== pointerId) return;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      if (stopNodeTrackRef.current === finish) stopNodeTrackRef.current = null;
      const drag = nodeDragRef.current;
      if (!drag.active) return;
      if (drag.moved) suppressClickRef.current = true;
      drag.active = false;
      drag.moved = false;
    };
    const move = (pointerEvent: PointerEvent) => {
      if (pointerEvent.pointerId !== pointerId) return;
      const drag = nodeDragRef.current;
      if (!drag.active) return;
      if ((pointerEvent.buttons & 1) === 0) {
        finish(pointerEvent);
        return;
      }
      const dx = (pointerEvent.clientX - drag.startX) / (viewRef.current.k || 1);
      const dy = (pointerEvent.clientY - drag.startY) / (viewRef.current.k || 1);
      if (!drag.moved && Math.hypot(dx, dy) < 4) return;
      drag.moved = true;
      const id = drag.id;
      const x = drag.originX + dx;
      const y = drag.originY + dy;
      setNodeOffsets((prev) => ({ ...prev, [id]: { x, y } }));
    };
    stopNodeTrackRef.current = () => finish();
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
  };

  const toggleFullscreen = () => {
    const shell = shellRef.current;
    if (!shell) return;
    if (document.fullscreenElement === shell) {
      const exit = document.exitFullscreen?.();
      void exit?.catch(() => undefined);
      return;
    }
    const enter = shell.requestFullscreen?.();
    void enter?.catch(() => undefined);
  };

  const onNodeClick = (nodeId: string) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    setSelectedId(nodeId);
  };

  const changeZoom = (direction: 1 | -1) => {
    const canvas = canvasRef.current;
    const rect = canvas?.getBoundingClientRect();
    const originX = rect ? rect.width / 2 : 0;
    const originY = rect ? rect.height / 2 : 0;
    const current = viewRef.current;
    const next = clampZoom(current.k + direction * 0.15);
    const worldX = (originX - current.x) / current.k;
    const worldY = (originY - current.y) / current.k;
    setZoom(next);
    setPan({ x: originX - worldX * next, y: originY - worldY * next });
  };

  if (alerts.length === 0) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        {loading ? <Spin /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData', '暂无数据')} />}
      </div>
    );
  }
  if (!payload) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (model.mode === 'not_purchased') {
    return (
      <div className="flex min-h-[420px] items-center justify-center px-6 text-center text-[var(--color-text-2)]" role="status">
        {model.message}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <Spin spinning={loading} wrapperClassName="flex h-full min-h-0 flex-1 flex-col [&>.ant-spin-container]:flex [&>.ant-spin-container]:h-full [&>.ant-spin-container]:min-h-0 [&>.ant-spin-container]:flex-1 [&>.ant-spin-container]:flex-col">
      <div
        ref={shellRef}
        data-testid="impact-topology-shell"
        className="flex h-full min-h-[420px] min-w-0 flex-1 overflow-hidden rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] [&:fullscreen]:h-screen [&:fullscreen]:w-screen [&:fullscreen]:rounded-none"
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {model.hint ? (
            <div className="px-3 pt-3 text-sm text-[var(--color-text-3)]" role="status">{model.hint}</div>
          ) : null}
          {model.quietOmitted > 0 && !drawOmitted ? (
            <button
              type="button"
              className="mx-3 mt-3 w-fit rounded px-1 text-left text-sm text-[var(--color-primary)] underline"
              onClick={() => setDrawOmitted(true)}
            >
              {copy.quietOmitted(model.quietOmitted)}
            </button>
          ) : null}
          <div
            ref={canvasRef}
            className={`relative min-h-0 flex-1 overflow-hidden ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
            data-testid="impact-topology-canvas"
            style={{ touchAction: 'none' }}
            onPointerDown={onCanvasPointerDown}
          >
              <div
                className="absolute left-0 top-0"
                data-testid="impact-topology-graph"
                style={{
                  width: placed.width,
                  height: placed.height,
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                  transformOrigin: '0 0',
                }}
              >
            <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
              {model.edges.map((edge) => {
                const source = placed.nodes.find((node) => node.id === edge.source);
                const target = placed.nodes.find((node) => node.id === edge.target);
                if (!source || !target) return null;
                const x1 = source.x + IMPACT_NODE_WIDTH / 2;
                const y1 = source.y + IMPACT_NODE_HEIGHT / 2;
                const x2 = target.x + IMPACT_NODE_WIDTH / 2;
                const y2 = target.y + IMPACT_NODE_HEIGHT / 2;
                return (
                  <g key={edge.id}>
                    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-border)" strokeWidth="1.5" />
                    {edge.label ? (
                      <text
                        x={(x1 + x2) / 2}
                        y={(y1 + y2) / 2 - 6}
                        fill="var(--color-text-3)"
                        fontSize="12"
                        textAnchor="middle"
                      >
                        {edge.label}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </svg>
            {placed.nodes.map((node) => {
              const accent = nodeAccent(node);
              const selectedNode = selected?.id === node.id;
              return (
                <button
                  key={node.id}
                  type="button"
                  data-kind={node.kind}
                  data-alert-state={node.alertState}
                  className="absolute cursor-grab rounded px-3 py-2 text-left active:cursor-grabbing"
                  style={nodeStyle(node, accent, selectedNode)}
                  onPointerDown={(event) => onNodePointerDown(node.id, event)}
                  onClick={() => onNodeClick(node.id)}
                >
                  <span
                    className="block truncate text-sm"
                    style={{ color: node.kind === 'unbound' ? PROTOTYPE_UNBOUND.title : 'var(--color-text-1)' }}
                  >
                    {node.label}
                  </span>
                  <span className="mt-1 block truncate text-xs" style={{ color: nodeCaptionColor(node, accent) }}>
                    {node.levelName ? `${node.levelName} · ` : ''}
                    {node.detail}
                  </span>
                </button>
              );
            })}
          </div>
            <div className="absolute bottom-3 right-3 z-10 flex flex-col overflow-hidden rounded border border-[var(--color-border)] bg-[var(--color-bg)]">
              <Button
                aria-label={fullscreen ? t('incidents.impactExitFullscreen', '退出全屏') : t('incidents.impactFullscreen', '全屏')}
                type="text"
                size="small"
                icon={fullscreen ? <FullscreenExitOutlined aria-hidden="true" /> : <FullscreenOutlined aria-hidden="true" />}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={toggleFullscreen}
              />
              <Button
                aria-label={t('incidents.impactZoomIn', '放大')}
                type="text"
                size="small"
                icon={<PlusOutlined aria-hidden="true" />}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => changeZoom(1)}
              />
              <Button
                aria-label={t('incidents.impactZoomOut', '缩小')}
                type="text"
                size="small"
                icon={<MinusOutlined aria-hidden="true" />}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => changeZoom(-1)}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4 px-3 py-3 text-xs text-[var(--color-text-2)]">
            <LegendLevels nodes={model.nodes} fallback={t('incidents.impactLegendAlert', '告警')} />
            <LegendSwatch label={t('incidents.impactLegendBridge', '桥接')} bridge />
            <LegendSwatch label={t('incidents.impactNoAlert', '无告警')} clear />
            <LegendSwatch label={t('incidents.impactLegendUnbound', '未绑定')} muted />
          </div>
        </div>
        {selected ? (
          <aside className="flex w-[28rem] max-w-[40%] shrink-0 flex-col overflow-hidden border-l border-[var(--color-border)]">
            <div className="border-b border-[var(--color-border)] px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs text-[var(--color-text-3)]">
                    {sidebarKind(selected.kind, t)}
                  </div>
                  <div className="mt-1 truncate text-base font-medium text-[var(--color-text-1)]">{selected.label}</div>
                </div>
                <Button
                  type="text"
                  size="small"
                  aria-label={t('alarms.close', '关闭')}
                  icon={<CloseOutlined aria-hidden="true" />}
                  onClick={() => setSelectedId(null)}
                />
              </div>
              {selected.relations.length > 0 ? (
                <ul className="mt-3 space-y-1 rounded bg-[var(--color-fill-2)] px-3 py-2 text-sm leading-6 text-[var(--color-text-2)]">
                  {selected.relations.map((relation, index) => (
                    <li key={`${relation}-${index}`} className="break-words">{relation}</li>
                  ))}
                </ul>
              ) : null}
              {selected.kind === 'bridge' ? (
                <div className="mt-3 space-y-2">
                  <div className="text-xs text-[var(--color-text-3)]">{t('incidents.impactViaBridge', '经由该对象连上的告警')}</div>
                  {selected.linkedObjects.map((object) => (
                    <div key={object.id}>
                      <div className="text-sm text-[var(--color-text-1)]">{object.label}</div>
                      <ul className="mt-1 space-y-1 text-sm text-[var(--color-text-2)]">
                        {object.alerts.map((alert) => (
                          <li key={alert.id}>{alert.title}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : null}
              {selected.kind === 'application' || selected.kind === 'system' ? (
                <div className="mt-3 text-xs leading-5 text-[var(--color-text-3)]">
                  {t('incidents.impactIncludesMembers', '计数包含成员当前告警，这些告警不会自动并入本事故')}
                </div>
              ) : null}
            </div>
            <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
              <div className="mb-2 text-xs text-[var(--color-text-3)]">{t('alarms.alert', '告警')}</div>
              {selected.kind === 'unbound' ? (
                <AlertTable
                  levels={levels}
                  items={selected.alerts.map((alert) => ({ id: alert.id, title: alert.title }))}
                />
              ) : loadAlerts ? (
                <>
                  <AlertTable
                    levels={levels}
                    items={alertListError || (!alertListLoading && alertItems.length === 0) ? [] : alertItems}
                    loading={alertListLoading}
                    empty={alertListLoading ? <span /> : (
                      <span role="status">
                        {alertListError
                          ? t('incidents.impactListFailed', '告警列表暂时打不开')
                          : selected.alertState === 'unknown' ? copy.alertUnknown : copy.noAlert}
                      </span>
                    )}
                  />
                  {alertTotal > 20 ? (
                    <Pagination
                      className="mt-3"
                      size="small"
                      current={alertPage}
                      pageSize={20}
                      total={alertTotal}
                      showSizeChanger={false}
                      onChange={(next) => setAlertPage(next)}
                    />
                  ) : null}
                </>
              ) : (
                <AlertTable
                  levels={levels}
                  items={selected.alerts.map((alert) => ({ id: alert.id, title: alert.title }))}
                  empty={<span role="status">{selected.alertState === 'unknown' ? copy.alertUnknown : copy.noAlert}</span>}
                />
              )}
            </div>
          </aside>
        ) : null}
      </div>
      </Spin>
    </div>
  );
};

function nodeAccent(node: ImpactGraphNode): string {
  if (node.kind === 'unbound' || node.alertState === 'unbound') return PROTOTYPE_UNBOUND.border;
  if (node.alertState === 'unknown') return 'var(--color-warning, #ff7d00)';
  if (node.alertState === 'active' || node.alertState === 'incident') return node.color || 'var(--color-border)';
  if (node.alertState === 'clear' && node.kind !== 'bridge') return 'var(--color-success, #27c274)';
  if (node.kind === 'bridge') return PROTOTYPE_BRIDGE.border;
  return node.color || 'var(--color-border)';
}

function nodeCaptionColor(node: ImpactGraphNode, accent: string): string {
  if (node.kind === 'unbound') return PROTOTYPE_UNBOUND.caption;
  if (node.kind === 'bridge' && node.alertState !== 'active') return PROTOTYPE_BRIDGE.caption;
  return accent;
}

function nodeStyle(node: ImpactGraphNode, accent: string, selected: boolean): React.CSSProperties {
  const backgroundColor = node.kind === 'unbound'
    ? PROTOTYPE_UNBOUND.background
    : node.kind === 'bridge' && node.alertState !== 'active'
      ? PROTOTYPE_BRIDGE.background
      : `color-mix(in srgb, ${accent} 16%, var(--color-bg-1))`;
  return {
    left: node.x,
    top: node.y,
    width: IMPACT_NODE_WIDTH,
    borderWidth: 1,
    borderStyle: node.kind === 'bridge' ? 'dashed' : 'solid',
    borderColor: accent,
    backgroundColor,
    boxShadow: selected ? `0 0 0 2px ${accent}` : undefined,
  };
}

function clampZoom(value: number): number {
  const clamped = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  return Math.round(clamped * 100) / 100;
}

function sidebarKind(kind: ImpactGraphNode['kind'], t: (key: string, fallback: string) => string): string {
  if (kind === 'bridge') return t('incidents.impactBridge', '桥接');
  if (kind === 'unbound') return t('incidents.impactUnbound', '未绑定 CMDB');
  if (kind === 'related') return t('incidents.impactRelated', '关联对象');
  if (kind === 'application') return t('incidents.impactApplication', '应用');
  if (kind === 'system') return t('incidents.impactSystem', '系统');
  return t('incidents.impactAlertObject', '告警对象');
}

const ALERT_STATUS_FALLBACK: Record<string, string> = {
  unassigned: '未分派',
  pending: '待响应',
  processing: '处理中',
  resolved: '已处理',
  closed: '已关闭',
  auto_close: '自动关闭',
  auto_recovery: '自动恢复',
};

function placeNodes(
  nodes: ImpactGraphNode[],
  offsets: Record<string, { x: number; y: number }>,
  width: number,
  height: number,
) {
  const shifted = nodes.map((node) => {
    const offset = offsets[node.id];
    return offset ? { ...node, x: node.x + offset.x, y: node.y + offset.y } : node;
  });
  if (shifted.length === 0) return { nodes: shifted, width, height };
  const minX = Math.min(0, ...shifted.map((node) => node.x));
  const minY = Math.min(0, ...shifted.map((node) => node.y));
  const placedNodes = shifted.map((node) => ({ ...node, x: node.x - minX, y: node.y - minY }));
  return {
    nodes: placedNodes,
    width: Math.max(width, ...placedNodes.map((node) => node.x + IMPACT_NODE_WIDTH + 24)),
    height: Math.max(height, ...placedNodes.map((node) => node.y + IMPACT_NODE_HEIGHT + 24)),
  };
}

function AlertTable({
  items,
  levels = [],
  loading = false,
  empty,
}: {
  items: ImpactAlertPage['items'];
  levels?: LevelItem[];
  loading?: boolean;
  empty?: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <Table
      bordered
      size="small"
      rowKey="id"
      tableLayout="fixed"
      pagination={false}
      loading={loading}
      dataSource={items}
      locale={{ emptyText: empty || t('incidents.impactNoAlert', '无告警') }}
      columns={[
        {
          title: t('alarms.level', '级别'),
          dataIndex: 'level',
          width: 72,
          ellipsis: true,
          render: (value: string | undefined) => {
            const level = levels.find((item) => String(item.level_id) === String(value));
            return level?.level_display_name || level?.level_name || '--';
          },
        },
        {
          title: t('alarms.state', '状态'),
          dataIndex: 'status',
          width: 88,
          ellipsis: true,
          render: (value: string | undefined) => (
            value ? t(`alarms.${value}`, ALERT_STATUS_FALLBACK[value] || value) : '--'
          ),
        },
        {
          title: t('alarms.title', '标题'),
          dataIndex: 'title',
          ellipsis: true,
          render: (value: string | undefined, alert: ImpactAlertPage['items'][number]) => {
            const href = alert.alert_id ? buildAlarmDetailUrl(window.location.origin, alert.alert_id) : '';
            const label = value || alert.alert_id || '';
            return href ? (
              <a className="text-[var(--color-primary)]" href={href} target="_blank" rel="noreferrer">
                {label}
              </a>
            ) : label;
          },
        },
        {
          title: t('incidents.impactBelonging', '归属'),
          dataIndex: 'in_incident',
          width: 96,
          render: (value: boolean | undefined) => {
            if (value == null) return '--';
            return value
              ? t('incidents.impactInIncident', '本事故')
              : t('incidents.impactOutsideBadge', '未入本事故');
          },
        },
      ]}
    />
  );
}

function LegendLevels({ nodes, fallback }: { nodes: ImpactGraphNode[]; fallback: string }) {
  const levels = nodes.filter((node) => node.kind === 'seed' && node.color);
  const unique: Array<{ name: string; color: string }> = [];
  levels.forEach((node) => {
    const name = node.levelName || fallback;
    if (unique.some((item) => item.name === name && item.color === node.color)) return;
    unique.push({ name, color: node.color || 'var(--color-border)' });
  });
  if (unique.length === 0) {
    return <LegendSwatch label={fallback} />;
  }
  return (
    <>
      {unique.map((item) => (
        <span key={`${item.name}-${item.color}`} className="inline-flex items-center gap-1">
          <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} />
          {item.name}
        </span>
      ))}
    </>
  );
}

function LegendSwatch({
  label,
  bridge = false,
  muted = false,
  clear = false,
}: {
  label: string;
  bridge?: boolean;
  muted?: boolean;
  clear?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <i
        className="inline-block h-2.5 w-2.5 rounded-sm"
        style={bridge
          ? { background: PROTOTYPE_BRIDGE.caption, border: `1px dashed ${PROTOTYPE_BRIDGE.border}` }
          : muted
            ? { background: PROTOTYPE_UNBOUND.background, border: `1px solid ${PROTOTYPE_UNBOUND.border}` }
            : clear
              ? { background: 'var(--color-success, #27c274)' }
              : { background: 'var(--color-fill-2)', border: '1px solid var(--color-border)' }}
      />
      {label}
    </span>
  );
}

export default ImpactTopologyView;
