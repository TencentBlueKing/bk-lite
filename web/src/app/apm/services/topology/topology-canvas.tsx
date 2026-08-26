'use client';

import { useEffect, useMemo, useState } from 'react';
import { formatCompactLatency, formatNumber, formatTopologyEdgeMetrics } from '@/app/apm/components/metric-format';
import ServiceLanguageIcon, { serviceLanguageLabel } from '@/app/apm/components/service-language-icon';
import {
  buildTopologyEdgeGeometry,
  hasReciprocalTopologyEdge,
  layoutForceTopology,
  layoutLayeredTopology,
  TOPOLOGY_CANVAS_SIZE,
  type PositionedApmTopologyNode,
} from '@/app/apm/services/topology/topology-layout';
import type { ApmTopologyEdge, ApmTopologyHealth, ApmTopologyNode } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

export type TopologyLayoutMode = 'layered' | 'force';

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

const NODE_RADIUS_MIN = 14;
const NODE_RADIUS_SPAN = 6;
const CANVAS_SURFACE_CLASS = [
  'relative h-[640px] w-full overflow-hidden bg-[var(--color-fill-1)]',
  '[background-size:24px_24px]',
  '[background-image:linear-gradient(to_right,color-mix(in_srgb,var(--color-border)_55%,transparent)_1px,transparent_1px),linear-gradient(to_bottom,color-mix(in_srgb,var(--color-border)_55%,transparent)_1px,transparent_1px)]',
].join(' ');

export default function TopologyCanvas({
  nodes,
  edges,
  keyword,
  zoom,
  layout = 'layered',
  focusNamespace,
  onNodeClick,
}: {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  keyword: string;
  zoom: number;
  layout?: TopologyLayoutMode;
  focusNamespace?: string;
  onNodeClick?: (node: ApmTopologyNode) => void;
}) {
  const { t } = useTranslation();
  const layoutKey = useMemo(
    () => `${layout}:${nodes.map((node) => node.id).join('|')}:${edges.map((edge) => `${edge.source}>${edge.target}`).join('|')}`,
    [edges, layout, nodes],
  );
  const [layoutResult, setLayoutResult] = useState<{ key: string; nodes: PositionedApmTopologyNode[] }>({
    key: '',
    nodes: [],
  });

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

  const positionedNodes = layoutResult.key === layoutKey ? layoutResult.nodes : [];
  const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
  const normalizedKeyword = keyword.trim().toLowerCase();
  const maxSpans = Math.max(...nodes.map((node) => node.sampled_spans), 1);
  const maxCalls = Math.max(...edges.map((edge) => edge.sampled_calls), 1);
  const edgePairs = new Set(edges.map((edge) => `${edge.source}\u0000${edge.target}`));
  const routing = layout === 'layered' ? 'polyline' : 'curve';
  const focusNodeIds = focusNamespace
    ? new Set(positionedNodes.filter((node) => node.service_namespace === focusNamespace).map((node) => node.id))
    : null;
  const nodeRadius = (sampledSpans: number) => NODE_RADIUS_MIN + (sampledSpans / maxSpans) * NODE_RADIUS_SPAN;

  return (
    <div className={CANVAS_SURFACE_CLASS} data-topology-surface="true">
      <svg
        aria-label={t('apm.topology.chartAria', 'APM 服务调用拓扑')}
        className="absolute inset-0 block h-full w-full"
        data-layout={layout}
        role="img"
        viewBox={`0 0 ${TOPOLOGY_CANVAS_SIZE.width} ${TOPOLOGY_CANVAS_SIZE.height}`}
      >
        <defs>
          {(['healthy', 'warning', 'critical'] as ApmTopologyHealth[]).map((health) => (
            <marker id={`apm-arrow-${health}`} key={health} markerHeight="7" markerUnits="userSpaceOnUse" markerWidth="7" orient="auto" refX="6" refY="3.5" viewBox="0 0 8 8">
              <path d="M 0 0 L 8 3.5 L 0 7 Z" fill="context-stroke" />
            </marker>
          ))}
        </defs>
        <g style={{ transform: `scale(${zoom})`, transformBox: 'fill-box', transformOrigin: 'center' }}>
        {edges.map((edge) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return null;
          const geometry = buildTopologyEdgeGeometry(
            { x: source.x, y: source.y, radius: nodeRadius(source.sampled_spans) },
            { x: target.x, y: target.y, radius: nodeRadius(target.sampled_spans) },
            hasReciprocalTopologyEdge(edge, edgePairs),
            routing,
          );
          const hasError = edge.error_calls > 0;
          const color = hasError
            ? topologyHealthColors.critical
            : edge.health === 'warning'
              ? topologyHealthColors.warning
              : 'color-mix(in srgb, var(--color-primary) 42%, var(--color-border))';
          const marker = hasError ? 'critical' : edge.health === 'warning' ? 'warning' : 'healthy';
          const strokeWidth = Math.max(1, Math.min(2.2, 0.9 + (edge.sampled_calls / maxCalls) * 1.2));
          return (
            <g data-source={edge.source} data-target={edge.target} key={`${edge.source}-${edge.target}`}>
              <title>{t('apm.topology.edgeTitle', '{source} 调用 {target}，调用 {calls} 次，平均耗时 {duration}，错误 {errors}', {
                source: source.service_name,
                target: target.service_name,
                calls: formatNumber(edge.sampled_calls),
                duration: formatCompactLatency(edge.average_duration_ms),
                errors: formatNumber(edge.error_calls),
              })}</title>
              <path
                d={geometry.path}
                fill="none"
                markerEnd={`url(#apm-arrow-${marker})`}
                stroke={color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={strokeWidth}
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
                y={geometry.labelY - 5}
              >
                {formatTopologyEdgeMetrics(edge)}
              </text>
            </g>
          );
        })}
        {positionedNodes.map((node) => {
          const matched = !normalizedKeyword || `${node.service_namespace} ${node.service_name}`.toLowerCase().includes(normalizedKeyword);
          const radius = nodeRadius(node.sampled_spans);
          const inFocus = !focusNodeIds || focusNodeIds.has(node.id);
          const iconSize = Math.max(12, Math.min(16, radius * 0.85));
          const languageTitle = serviceLanguageLabel(node.language, t('apm.language.unknown', '未知'));
          return (
            <g
              key={node.id}
              aria-label={t('apm.topology.nodeAria', '{name}，{health}，时间窗内观测 {spans} 个 Span', {
                name: node.service_name,
                health: t(topologyHealthI18n[node.health].id, topologyHealthI18n[node.health].fallback),
                spans: node.sampled_spans,
              })}
              opacity={matched ? (inFocus ? 1 : 0.55) : 0.18}
              role={onNodeClick ? 'link' : undefined}
              tabIndex={onNodeClick ? 0 : undefined}
              style={{
                cursor: onNodeClick ? 'pointer' : undefined,
                filter: inFocus ? undefined : 'grayscale(1)',
              }}
              transform={`translate(${node.x},${node.y})`}
              onClick={() => onNodeClick?.(node)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onNodeClick?.(node);
                }
              }}
            >
              <title>{t('apm.topology.nodeTitle', '{name}\n{language} · 观测 Span {spans} · 错误 {errors}', {
                name: node.service_name,
                language: languageTitle,
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
                stroke={inFocus ? topologyHealthColors[node.health] : 'var(--color-text-4)'}
                strokeDasharray={inFocus ? undefined : '4 3'}
                strokeWidth={node.health === 'critical' ? 2.5 : 1.6}
              />
              <ServiceLanguageIcon
                language={node.language}
                size={iconSize}
                x={-iconSize / 2}
                y={-iconSize / 2}
              />
              <text
                fill={node.health === 'critical' ? 'var(--color-fail)' : 'var(--color-text-1)'}
                fontSize="12"
                fontWeight="600"
                textAnchor="start"
                x={radius + 8}
                y={-1}
              >
                {node.service_name}
              </text>
              <text fill="var(--color-text-3)" fontSize="10" textAnchor="start" x={radius + 8} y={13}>
                {node.service_namespace || t('apm.common.unsetNamespace', '未设置 namespace')} · {node.environment}
              </text>
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
