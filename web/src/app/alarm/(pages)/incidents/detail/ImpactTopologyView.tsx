'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Empty, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
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

interface ImpactTopologyViewProps {
  alerts: AlarmTableDataItem[];
  payload: ImpactTopologyPayload | null;
  loading?: boolean;
  levels?: LevelItem[];
  levelColors?: Record<string, string>;
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
  }), [t]);
  const model = useMemo(
    () => buildImpactGraph(alerts, payload, levels, levelColors, copy),
    [alerts, payload, levels, levelColors, copy],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const dragRef = useRef({ active: false, moved: false, startX: 0, startY: 0, originX: 0, originY: 0 });
  const selected = model.nodes.find((node) => node.id === selectedId) || null;
  const layoutKey = model.nodes.map((node) => `${node.id}:${node.x}:${node.y}`).join('|');
  useEffect(() => {
    setPan({ x: 0, y: 0 });
  }, [layoutKey]);

  const onCanvasPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // A pointer id the browser will not capture still pans while the pointer stays on the canvas.
    }
  };

  const onCanvasPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag.active) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    setPanning(true);
    setPan({ x: drag.originX + dx, y: drag.originY + dy });
  };

  const onCanvasPointerUp = () => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    setPanning(false);
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
      <div className="flex h-full min-h-[420px] min-w-0 flex-1 overflow-hidden rounded border border-[var(--color-border)] bg-[var(--color-bg-1)]">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {model.hint ? (
            <div className="px-3 pt-3 text-sm text-[var(--color-text-3)]" role="status">{model.hint}</div>
          ) : null}
          <div
            className={`min-h-0 flex-1 overflow-hidden ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
            data-testid="impact-topology-canvas"
            style={{ touchAction: 'none' }}
            onPointerDown={onCanvasPointerDown}
            onPointerMove={onCanvasPointerMove}
            onPointerUp={onCanvasPointerUp}
            onPointerCancel={onCanvasPointerUp}
          >
            <div className="flex min-h-full min-w-full items-center justify-center p-3">
              <div
                className="relative shrink-0"
                data-testid="impact-topology-graph"
                style={{ width: model.width, height: model.height, transform: `translate(${pan.x}px, ${pan.y}px)` }}
              >
            <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
              {model.edges.map((edge) => {
                const source = model.nodes.find((node) => node.id === edge.source);
                const target = model.nodes.find((node) => node.id === edge.target);
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
            {model.nodes.map((node) => {
              const accent = nodeAccent(node);
              const selectedNode = selected?.id === node.id;
              return (
                <button
                  key={node.id}
                  type="button"
                  data-kind={node.kind}
                  className="absolute rounded px-3 py-2 text-left"
                  style={nodeStyle(node, accent, selectedNode)}
                  onClick={() => {
                    if (dragRef.current.moved) return;
                    setSelectedId(node.id);
                  }}
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
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4 px-3 py-3 text-xs text-[var(--color-text-2)]">
            <LegendLevels nodes={model.nodes} fallback={t('incidents.impactLegendAlert', '告警')} />
            <LegendSwatch label={t('incidents.impactLegendBridge', '桥接')} bridge />
            <LegendSwatch label={t('incidents.impactLegendUnbound', '未绑定')} muted />
          </div>
        </div>
        {selected ? (
          <aside className="w-80 shrink-0 overflow-auto border-l border-[var(--color-border)] p-4">
            <div className="text-xs text-[var(--color-text-3)]">
              {selected.kind === 'bridge'
                ? t('incidents.impactBridge', '桥接')
                : selected.kind === 'unbound'
                  ? t('incidents.impactUnbound', '未绑定 CMDB')
                  : t('incidents.impactAlertObject', '告警对象')}
            </div>
            <div className="mt-1 text-base text-[var(--color-text-1)]">{selected.label}</div>
            {selected.relations.length > 0 ? (
              <ul className="mt-4 space-y-2 text-sm text-[var(--color-text-2)]">
                {selected.relations.map((relation, index) => (
                  <li key={`${relation}-${index}`}>{relation}</li>
                ))}
              </ul>
            ) : null}
            {selected.kind === 'bridge' ? (
              <div className="mt-4 space-y-3">
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
            ) : selected.alerts.length > 0 ? (
              <div className="mt-4">
                <div className="mb-2 text-xs text-[var(--color-text-3)]">{t('alarms.alert', '告警')}</div>
                <ul className="space-y-2 text-sm text-[var(--color-text-1)]">
                  {selected.alerts.map((alert) => (
                    <li key={alert.id}>{alert.title}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </aside>
        ) : null}
      </div>
      </Spin>
    </div>
  );
};

function nodeAccent(node: ImpactGraphNode): string {
  if (node.kind === 'bridge') return PROTOTYPE_BRIDGE.border;
  if (node.kind === 'unbound') return PROTOTYPE_UNBOUND.border;
  return node.color || 'var(--color-border)';
}

function nodeCaptionColor(node: ImpactGraphNode, accent: string): string {
  if (node.kind === 'bridge') return PROTOTYPE_BRIDGE.caption;
  if (node.kind === 'unbound') return PROTOTYPE_UNBOUND.caption;
  return accent;
}

function nodeStyle(node: ImpactGraphNode, accent: string, selected: boolean): React.CSSProperties {
  const backgroundColor = node.kind === 'bridge'
    ? PROTOTYPE_BRIDGE.background
    : node.kind === 'unbound'
      ? PROTOTYPE_UNBOUND.background
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
}: {
  label: string;
  bridge?: boolean;
  muted?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <i
        className="inline-block h-2.5 w-2.5 rounded-sm"
        style={bridge
          ? { background: PROTOTYPE_BRIDGE.caption, border: `1px dashed ${PROTOTYPE_BRIDGE.border}` }
          : muted
            ? { background: PROTOTYPE_UNBOUND.background, border: `1px solid ${PROTOTYPE_UNBOUND.border}` }
            : { background: 'var(--color-fill-2)', border: '1px solid var(--color-border)' }}
      />
      {label}
    </span>
  );
}

export default ImpactTopologyView;
