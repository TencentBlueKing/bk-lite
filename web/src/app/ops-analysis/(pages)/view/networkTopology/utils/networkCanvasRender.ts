/**
 * 网络拓扑画布渲染纯函数：连线样式、节点指纹、编辑态端口/工具显隐。
 * 大图下避免全量流动动画、textWrap/阴影和全端口常亮。
 */

export const NETWORK_NODE_PORT_IDS = [
  'port-top',
  'port-right',
  'port-bottom',
  'port-left',
] as const;

export const NETWORK_EDGE_FLOW_CLASS = 'network-edge-flow';
export const NETWORK_NODE_DETAIL_CLASS = 'nt-node-detail';
export const NETWORK_CANVAS_COMPACT_CLASS = 'network-canvas-compact';
export const NETWORK_CANVAS_COMPACT_SCALE = 0.5;

export type NetworkLinkPaintStatus = 'normal' | 'critical' | 'unknown';

export interface NetworkLinkLineAttrs {
  stroke: string;
  strokeWidth: number;
  strokeLinecap: 'round';
  strokeLinejoin: 'round';
  strokeDasharray: string | null;
  class: string;
  targetMarker: { name: string; size: number };
}

export const strokeFromLinkStatus = (
  status?: NetworkLinkPaintStatus,
): string => {
  if (status === 'critical') return '#dc2626';
  if (status === 'normal') return '#16a34a';
  return '#64748b';
};

/**
 * 默认实线。仅告警线做流动虚线；草稿/未选口用静态虚线，避免 370 条线同时 CSS 动画。
 */
export const buildLinkLineAttrs = (
  status?: NetworkLinkPaintStatus,
  options?: { pending?: boolean },
): NetworkLinkLineAttrs => {
  const pending = Boolean(options?.pending);
  const animate = !pending && status === 'critical';
  const dashed = pending || animate;
  return {
    stroke: strokeFromLinkStatus(status),
    strokeWidth: status === 'critical' ? 2 : 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    strokeDasharray: dashed ? '5 3' : null,
    class: animate ? NETWORK_EDGE_FLOW_CLASS : '',
    targetMarker: {
      name: 'block',
      size: 8,
    },
  };
};

export const shouldShowNodePorts = (
  editMode: boolean,
  hoveredNodeId: string | null,
  nodeId: string,
  options?: { connecting?: boolean },
): boolean =>
  editMode && (Boolean(options?.connecting) || hoveredNodeId === nodeId);

export const isTransientConnectingEdge = (
  data: { connecting?: boolean; link?: { id?: string } } | null | undefined,
): boolean => Boolean(data?.connecting);

export const shouldShowEdgeTools = (
  editMode: boolean,
  selectedEdgeId: string | null,
  edgeId: string,
): boolean => editMode && selectedEdgeId === edgeId;

export const shouldUseCompactNodeDetail = (scale: number): boolean =>
  scale < NETWORK_CANVAS_COMPACT_SCALE;

export const buildNodeRuntimeFingerprint = (
  node: {
    id: string;
    bk_inst_name?: string;
    ip_addr?: string;
    plugin_template_name?: string;
    bk_obj_id?: string;
    metrics: ReadonlyArray<{
      metric_field: string;
      result_table_id: string;
      display_name?: string;
    }>;
  },
  runtime:
    | {
        outer_color?: string | null;
        metrics?: ReadonlyArray<{
          metric_field?: string;
          result_table_id?: string;
          value?: unknown;
          status?: string;
        }>;
      }
    | undefined,
  options?: { editMode?: boolean; compact?: boolean },
): string => {
  const metricKey = node.metrics
    .map((metric) => {
      const hit = runtime?.metrics?.find(
        (item) =>
          item.metric_field === metric.metric_field &&
          item.result_table_id === metric.result_table_id,
      );
      return `${metric.metric_field}:${metric.result_table_id}:${hit?.status ?? ''}:${String(hit?.value ?? '')}`;
    })
    .join('|');
  return [
    node.id,
    node.bk_inst_name ?? '',
    node.ip_addr ?? '',
    node.plugin_template_name ?? node.bk_obj_id ?? '',
    runtime?.outer_color ?? '',
    options?.editMode ? '1' : '0',
    options?.compact ? '1' : '0',
    String(node.metrics.length),
    metricKey,
  ].join('::');
};

export const buildLinkRuntimeFingerprint = (
  link: {
    id: string;
    source_node_id: string;
    target_node_id: string;
    source_port_id?: string;
    target_port_id?: string;
    is_draft?: boolean;
    vertices?: ReadonlyArray<{ x: number; y: number }>;
  },
  runtime?: { status?: NetworkLinkPaintStatus },
): string => {
  const vertices = (link.vertices ?? [])
    .map((point) => `${Math.round(point.x)}:${Math.round(point.y)}`)
    .join(',');
  return [
    link.id,
    link.source_node_id,
    link.target_node_id,
    link.source_port_id ?? '',
    link.target_port_id ?? '',
    link.is_draft ? '1' : '0',
    runtime?.status ?? '',
    vertices,
  ].join('::');
};
