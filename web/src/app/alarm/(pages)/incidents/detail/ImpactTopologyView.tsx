'use client';

import React, { useMemo, useState } from 'react';
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
  const selected = model.nodes.find((node) => node.id === selectedId) || null;

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
    <Spin spinning={loading}>
      <div className="flex min-h-[420px] overflow-hidden rounded border border-[var(--color-border)] bg-[var(--color-bg-1)]">
        <div className="min-w-0 flex-1 overflow-auto p-3">
          {model.hint ? (
            <div className="mb-3 text-sm text-[var(--color-text-3)]" role="status">{model.hint}</div>
          ) : null}
          <div className="relative" style={{ width: model.width, height: model.height }}>
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
            {model.nodes.map((node) => (
              <button
                key={node.id}
                type="button"
                data-kind={node.kind}
                className={`absolute rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-2 text-left ${
                  node.kind === 'bridge' ? 'border-dashed' : ''
                } ${node.kind === 'unbound' ? 'text-[var(--color-text-3)]' : 'text-[var(--color-text-1)]'} ${
                  selected?.id === node.id ? 'shadow-[0_0_0_2px_var(--color-primary)]' : ''
                }`}
                style={nodeStyle(node)}
                onClick={() => setSelectedId(node.id)}
              >
                <span className="block truncate text-sm text-[var(--color-text-1)]">{node.label}</span>
                <span className="mt-1 block truncate text-xs text-[var(--color-text-3)]">
                  {node.levelName ? `${node.levelName} · ` : ''}
                  {node.detail}
                </span>
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-[var(--color-text-2)]">
            <LegendLevels nodes={model.nodes} fallback={t('incidents.impactLegendAlert', '告警')} />
            <LegendSwatch label={t('incidents.impactLegendBridge', '桥接')} dashed />
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
  );
};

function nodeStyle(node: ImpactGraphNode): React.CSSProperties {
  return {
    left: node.x,
    top: node.y,
    width: IMPACT_NODE_WIDTH,
    borderColor: node.kind === 'seed' ? (node.color || 'var(--color-border)') : undefined,
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

function LegendSwatch({ label, dashed = false, muted = false }: { label: string; dashed?: boolean; muted?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <i
        className={`inline-block h-2.5 w-2.5 rounded-sm border border-[var(--color-border)] ${
          dashed ? 'border-dashed' : ''
        } ${muted ? 'bg-[var(--color-fill-2)]' : ''}`}
      />
      {label}
    </span>
  );
}

export default ImpactTopologyView;
