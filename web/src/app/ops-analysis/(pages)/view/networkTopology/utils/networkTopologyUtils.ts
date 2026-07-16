/**
 * 网络拓扑 view_sets 数据模型助手(depth: 浅层,无业务规则)。
 * 与 utils/nodeStatus.ts 等不同,这是单纯的 ID / 字符串转换。
 */

import type {
  NetworkTopologyNode,
  NetworkTopologyLink,
  NetworkNodeLibraryItem,
  NetworkTopologyMetric,
  NetworkMetricAggregateType,
  NetworkMetricConditionFilter,
  NetworkMetricDisplayMode,
  NetworkMetricRuntime,
  NetworkNodeRuntime,
  NetworkLinkRuntime,
  NetworkInterfaceRuntime,
} from '@/app/ops-analysis/types/networkTopology';
import { formatNetworkMetricValue } from './metricValueFormat';
import { resolveActiveThreshold } from './nodeStatus';

/** 节点的客户端唯一 ID —— 与 WeOps 归一化字段一致:`bk_obj_id:bk_inst_id`。 */
export const buildNetworkNodeClientId = (
  node: Pick<NetworkTopologyNode, 'bk_obj_id' | 'bk_inst_id'> | NetworkNodeLibraryItem,
): string => `${node.bk_obj_id}:${node.bk_inst_id}`;

/** 用 WeOps 节点库条目构造一个画布节点(position 由调用方提供)。 */
export const buildNetworkTopologyNode = (
  item: NetworkNodeLibraryItem,
  source: NetworkTopologyNode['network_collect_instance_id'] extends never
    ? never
    : Pick<
        NetworkTopologyNode,
        | 'network_collect_task_id'
        | 'network_collect_instance_id'
        | 'plugin_group_id'
        | 'plugin_group_name'
        | 'plugin_template_id'
        | 'plugin_template_name'
      >,
  position: { x: number; y: number },
): NetworkTopologyNode => ({
  id: buildNetworkNodeClientId(item),
  bk_obj_id: item.bk_obj_id,
  bk_inst_id: item.bk_inst_id,
  bk_inst_name: item.bk_inst_name,
  ip_addr: item.ip_addr ?? '',
  network_collect_task_id: Number(source.network_collect_task_id ?? 0),
  network_collect_instance_id: Number(source.network_collect_instance_id ?? 0),
  plugin_group_id: source.plugin_group_id ?? null,
  plugin_group_name: source.plugin_group_name ?? null,
  plugin_template_id: source.plugin_template_id,
  plugin_template_name: source.plugin_template_name ?? null,
  position,
  metrics: [],
});

const runtimeMetricKey = (
  metric: Pick<
    NetworkMetricRuntime,
    'metric_field' | 'result_table_id' | 'request_id' | 'sort_order'
  >,
): string => {
  if (metric.request_id) return metric.request_id;
  return `${metric.sort_order ?? 0}::${metric.metric_field}::${metric.result_table_id}`;
};

export const mergeNetworkTopologyRuntimeMetrics = (
  base: ReadonlyArray<NetworkMetricRuntime>,
  incoming: ReadonlyArray<NetworkMetricRuntime>,
): NetworkMetricRuntime[] => {
  const map = new Map<string, NetworkMetricRuntime>();
  base.forEach((metric) => map.set(runtimeMetricKey(metric), metric));
  incoming.forEach((metric) => map.set(runtimeMetricKey(metric), metric));
  return Array.from(map.values());
};

export const mergeNetworkTopologyRuntimeNodes = (
  baseRuntimeNodes: ReadonlyArray<NetworkNodeRuntime>,
  nodes: ReadonlyArray<NetworkTopologyNode>,
  runtimeMetricOverrides: Record<string, NetworkMetricRuntime[]>,
): NetworkNodeRuntime[] => {
  if (Object.keys(runtimeMetricOverrides).length === 0) {
    return [...baseRuntimeNodes];
  }
  const nodeById = new Map<string, NetworkTopologyNode>();
  nodes.forEach((node) => nodeById.set(node.id, node));
  const byId = new Map<string, NetworkNodeRuntime>();
  baseRuntimeNodes.forEach((node) => byId.set(node.id, node));
  Object.entries(runtimeMetricOverrides).forEach(([nodeId, metrics]) => {
    const node = nodeById.get(nodeId);
    const runtimeId = node ? buildNetworkNodeClientId(node) : nodeId;
    const existing = byId.get(runtimeId);
    byId.set(runtimeId, {
      id: runtimeId,
      outer_color: existing?.outer_color ?? null,
      status: existing?.status ?? 'unknown',
      interface_summary: existing?.interface_summary,
      error_code: existing?.error_code,
      error_message: existing?.error_message,
      metrics: mergeNetworkTopologyRuntimeMetrics(existing?.metrics ?? [], metrics),
    });
  });
  return Array.from(byId.values());
};

/** 把节点列表中指定 id 的节点 metrics 替换。 */
export const updateNodeMetrics = (
  nodes: ReadonlyArray<NetworkTopologyNode>,
  nodeId: string,
  metrics: NetworkTopologyMetric[],
): NetworkTopologyNode[] =>
  nodes.map((node) =>
    node.id === nodeId
      ? {
        ...node,
        metrics: metrics.map((metric, index) => ({
          ...metric,
          sort_order: metric.sort_order ?? index,
        })),
      }
      : node,
  );

export interface NetworkMetricDraftOption {
  metric_field: string;
  result_table_id: string;
  display_name: string;
  unit: string;
}

export interface NetworkMetricDraftInput {
  metricOption: NetworkMetricDraftOption;
  displayMode?: NetworkMetricDisplayMode;
  aggregateType?: NetworkMetricAggregateType;
  dimensions?: Record<string, string | null | undefined>;
  conditionFilter?: ReadonlyArray<{
    dimension_id?: string | null;
    value?: ReadonlyArray<string | null | undefined> | string | null;
  }>;
  thresholds: ReadonlyArray<{ value: string | number; color?: string | null }>;
  sortOrder: number;
}

const normalizeConditionFilterValues = (
  value: ReadonlyArray<string | null | undefined> | string | null | undefined,
): string[] => {
  const rawValues = Array.isArray(value) ? value : [value];
  return Array.from(
    new Set(
      rawValues
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter(Boolean),
    ),
  );
};

export const normalizeNetworkMetricConditionFilter = (
  conditionFilter?: NetworkMetricDraftInput['conditionFilter'],
): NetworkMetricConditionFilter[] =>
  (conditionFilter ?? []).reduce<NetworkMetricConditionFilter[]>((acc, item) => {
    const dimensionId =
      typeof item.dimension_id === 'string' ? item.dimension_id.trim() : '';
    const values = normalizeConditionFilterValues(item.value);
    if (!dimensionId || values.length === 0) return acc;
    acc.push({ dimension_id: dimensionId, value: values });
    return acc;
  }, []);

export const normalizeNetworkTopologyMetricOrder = (
  metrics: ReadonlyArray<NetworkTopologyMetric>,
): NetworkTopologyMetric[] =>
  [...metrics]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((metric, index) => ({ ...metric, sort_order: index }));

export const buildNetworkTopologyMetricDraft = ({
  metricOption,
  displayMode = 'aggregate',
  aggregateType = 'sum',
  dimensions = {},
  conditionFilter = [],
  thresholds,
  sortOrder,
}: NetworkMetricDraftInput): NetworkTopologyMetric => {
  const resolvedDisplayMode: NetworkMetricDisplayMode =
    displayMode === 'dimension' ? 'dimension' : 'aggregate';
  const resolvedConditionFilter = normalizeNetworkMetricConditionFilter(
    resolvedDisplayMode === 'dimension' ? conditionFilter : [],
  );
  const resolvedDimensions = Object.entries(dimensions).reduce<Record<string, string>>(
    (acc, [key, value]) => {
      if (
        resolvedDisplayMode !== 'dimension' ||
        resolvedConditionFilter.length > 0
      ) {
        return acc;
      }
      if (typeof value === 'string' && value.length > 0) {
        acc[key] = value;
      }
      return acc;
    },
    {},
  );

  return {
    metric_field: metricOption.metric_field,
    result_table_id: metricOption.result_table_id,
    display_name: metricOption.display_name,
    unit: metricOption.unit,
    display_mode: resolvedDisplayMode,
    aggregate_type: aggregateType,
    dimensions: resolvedDimensions,
    condition_filter: resolvedConditionFilter,
    sort_order: sortOrder,
    thresholds: thresholds
      .filter((threshold) => threshold.value !== '' && threshold.value !== null && threshold.value !== undefined)
      .map((threshold) => ({
        value: Number(threshold.value),
        color: threshold.color || '#000000',
      })),
  };
};

export const replaceNetworkTopologyMetricDraft = (
  metrics: ReadonlyArray<NetworkTopologyMetric>,
  sortOrder: number,
  nextMetric: NetworkTopologyMetric,
): NetworkTopologyMetric[] =>
  normalizeNetworkTopologyMetricOrder(
    metrics.map((metric) =>
      metric.sort_order === sortOrder
        ? { ...nextMetric, sort_order: sortOrder }
        : metric,
    ),
  );

export interface NetworkTopologyLinkTerminal {
  cell: string;
  port?: string;
}

const buildLinkTerminal = (
  cell: string,
  port: unknown,
): NetworkTopologyLinkTerminal => {
  if (typeof port === 'string' && port.trim().length > 0) {
    return { cell, port };
  }
  return { cell };
};

export const buildNetworkTopologyLinkTerminals = (
  link: Pick<
    NetworkTopologyLink,
    'source_node_id' | 'target_node_id' | 'source_port_id' | 'target_port_id'
  >,
): { source: NetworkTopologyLinkTerminal; target: NetworkTopologyLinkTerminal } => ({
  source: buildLinkTerminal(link.source_node_id, link.source_port_id),
  target: buildLinkTerminal(link.target_node_id, link.target_port_id),
});

export interface NetworkTopologyLinkRenderOptions {
  connector: { name: 'normal' };
  vertices: Array<{ x: number; y: number }>;
}

export const buildNetworkTopologyLinkRenderOptions = (
  link: Pick<NetworkTopologyLink, 'vertices'>,
): NetworkTopologyLinkRenderOptions => {
  return {
    connector: { name: 'normal' },
    vertices: (link.vertices ?? [])
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
      .map((point) => ({ x: point.x, y: point.y })),
  };
};

export interface NodeDetailMetricRow {
  key: string;
  label: string;
  value: string;
  color?: string;
}

export interface BoundMetricConfigLabels {
  aggregate: string;
  dimension: string;
  aggregateTypes: Record<NetworkMetricAggregateType, string>;
}

export interface BoundMetricConfigRow {
  key: string;
  label: string;
  scopeText: string;
  thresholds: Array<{ value: number; color: string }>;
}

export interface NodeDetailPortRow {
  key: string;
  name: string;
  status: 'up' | 'down' | 'testing' | 'unknown';
}

export interface LinkDetailPortRow {
  key: string;
  sourceName: string;
  sourceStatus: 'up' | 'down' | 'testing' | 'unknown';
  targetName: string;
  targetStatus: 'up' | 'down' | 'testing' | 'unknown';
}

export interface LinkInterfaceMetricRow {
  key: string;
  interfaceName: string;
  metricLabel: string;
  value: string;
}

export const DEFAULT_LINK_INTERFACE_METRICS = [
  'ifInOctets_5min',
  'ifOutOctets_5min',
  'ifHighSpeed',
];

export const PORT_VIEW_INTERFACE_METRIC_FIELDS = [
  'ifInOctets_5min',
  'ifOutOctets_5min',
  'ifHighSpeed',
  'ifOutDiscards_5min',
  'ifInDiscards_5min',
  'ifInErrors_5min',
  'ifOutErrors_5min',
];

export const metricRuntimeRequestId = (
  nodeId: string,
  metric: Pick<NetworkTopologyMetric, 'metric_field' | 'result_table_id' | 'sort_order'>,
): string =>
  `${nodeId}::${metric.sort_order ?? 0}::${metric.metric_field}::${metric.result_table_id}`;

export const findNetworkTopologyMetricRuntime = (
  node: NetworkTopologyNode,
  metric: NetworkTopologyMetric,
  runtime: NetworkNodeRuntime | undefined,
): NetworkMetricRuntime | undefined => {
  const matches =
    runtime?.metrics.filter(
      (item) =>
        item.metric_field === metric.metric_field &&
        item.result_table_id === metric.result_table_id,
    ) ?? [];
  const byRequestId = matches.find(
    (item) => item.request_id === metricRuntimeRequestId(node.id, metric),
  );
  if (byRequestId) return byRequestId;
  const bySortOrder = matches.find((item) => item.sort_order === metric.sort_order);
  if (bySortOrder) return bySortOrder;
  return matches.length === 1 ? matches[0] : undefined;
};

export const isMetricRuntimeLoading = (
  node: NetworkTopologyNode,
  metric: NetworkTopologyMetric,
  runtime: NetworkNodeRuntime | undefined,
): boolean =>
  findNetworkTopologyMetricRuntime(node, metric, runtime)?.status === 'loading';

export const buildNodeDetailMetricRows = (
  node: NetworkTopologyNode,
  runtime: NetworkNodeRuntime | undefined,
): NodeDetailMetricRow[] =>
  node.metrics.map((metric) => {
    const runtimeMetric = findNetworkTopologyMetricRuntime(node, metric, runtime);
    const value =
      !runtimeMetric ||
      runtimeMetric.status === 'error' ||
      runtimeMetric.value === null ||
      runtimeMetric.value === undefined
        ? '--'
        : formatNetworkMetricValue(runtimeMetric.value, runtimeMetric.unit, {
          fallbackUnit: metric.unit,
        });
    return {
      key: `${metric.sort_order ?? 0}::${metric.metric_field}::${metric.result_table_id}`,
      label: metric.display_name || metric.metric_field,
      value,
      color: resolveActiveThreshold(metric, runtimeMetric)?.color,
    };
  });

export const buildBoundMetricConfigRows = (
  metrics: ReadonlyArray<NetworkTopologyMetric>,
  labels: BoundMetricConfigLabels,
): BoundMetricConfigRow[] =>
  normalizeNetworkTopologyMetricOrder(metrics).map((metric) => {
    const hasConditionFilter = (metric.condition_filter ?? []).length > 0;
    const displayMode =
      metric.display_mode ??
      (hasConditionFilter || Object.keys(metric.dimensions ?? {}).length > 0
        ? 'dimension'
        : 'aggregate');
    const aggregateType = metric.aggregate_type ?? 'last';
    const conditionText = (metric.condition_filter ?? [])
      .map((item) => `${item.dimension_id}=${item.value.join(',')}`)
      .join(' · ');
    const dimensionText = Object.entries(metric.dimensions || {})
      .map(([key, value]) => `${key}=${value}`)
      .join(' · ');
    return {
      key: `${metric.sort_order ?? 0}::${metric.metric_field}::${metric.result_table_id}`,
      label: metric.display_name || metric.metric_field,
      scopeText:
        displayMode === 'aggregate'
          ? `${labels.aggregate} / ${labels.aggregateTypes[aggregateType]}`
          : `${labels.dimension} / ${labels.aggregateTypes[aggregateType]}${
              conditionText || dimensionText
                ? ` · ${conditionText || dimensionText}`
                : ''
            }`,
      thresholds: (metric.thresholds ?? []).map((threshold) => ({
        value: threshold.value,
        color: threshold.color,
      })),
    };
  });

const findRuntimeInterface = (
  runtime: NetworkLinkRuntime | undefined,
  endpoint: 'source' | 'target',
  ref: { bk_inst_id: number; interface_name: string },
): NetworkInterfaceRuntime | undefined =>
  runtime?.interfaces.find((item) => {
    const sameEndpoint = !item.endpoint || item.endpoint === endpoint;
    const sameId = item.bk_inst_id === ref.bk_inst_id;
    const sameName = item.interface_name === ref.interface_name;
    return sameEndpoint && (sameId || sameName);
  });

export const buildNodeDetailPortRows = (
  node: NetworkTopologyNode,
  links: ReadonlyArray<NetworkTopologyLink>,
  runtimeLinks: ReadonlyArray<NetworkLinkRuntime>,
): NodeDetailPortRow[] => {
  const rows: NodeDetailPortRow[] = [];
  links.forEach((link) => {
    const endpoint =
      link.source_node_id === node.id
        ? 'source'
        : link.target_node_id === node.id
          ? 'target'
          : null;
    if (!endpoint) return;
    const runtime = runtimeLinks.find((item) => item.id === link.id);
    link.port_pairs.forEach((pair) => {
      const ref =
        endpoint === 'source' ? pair.source_interface : pair.target_interface;
      if (!ref?.bk_inst_id || !ref.interface_name) return;
      const runtimeInterface = findRuntimeInterface(runtime, endpoint, ref);
      rows.push({
        key: `${link.id}:${endpoint}:${ref.bk_inst_id}`,
        name: ref.interface_name,
        status: normalizeInterfaceStatus(
          runtimeInterface?.oper_status ?? runtimeInterface?.admin_status,
        ),
      });
    });
  });
  return rows;
};

export const buildLinkDetailPortRows = (
  link: NetworkTopologyLink,
  runtime: NetworkLinkRuntime | undefined,
): LinkDetailPortRow[] =>
  link.port_pairs.map((pair, index) => {
    const sourceRuntime = findRuntimeInterface(
      runtime,
      'source',
      pair.source_interface,
    );
    const targetRuntime = findRuntimeInterface(
      runtime,
      'target',
      pair.target_interface,
    );
    return {
      key: `${link.id}:${index}`,
      sourceName: pair.source_interface.interface_name || '--',
      sourceStatus: normalizeInterfaceStatus(
        sourceRuntime?.oper_status ?? sourceRuntime?.admin_status,
      ),
      targetName: pair.target_interface.interface_name || '--',
      targetStatus: normalizeInterfaceStatus(
        targetRuntime?.oper_status ?? targetRuntime?.admin_status,
      ),
    };
  });

export const normalizeLinkInterfaceMetrics = (
  fields: ReadonlyArray<string> | undefined,
): string[] => {
  const allowed = new Set(PORT_VIEW_INTERFACE_METRIC_FIELDS);
  const seen = new Set<string>();
  return (fields ?? []).reduce<string[]>((acc, field) => {
    if (!allowed.has(field) || seen.has(field)) return acc;
    seen.add(field);
    acc.push(field);
    return acc;
  }, []);
};

export const buildLinkInterfaceMetricRows = (
  link: NetworkTopologyLink,
  runtime: NetworkLinkRuntime | undefined,
  labels: Record<string, string>,
): LinkInterfaceMetricRow[] => {
  const selectedMetrics = normalizeLinkInterfaceMetrics(link.interface_metrics);
  if (selectedMetrics.length === 0) return [];
  const runtimeInterfaces = runtime?.interfaces ?? [];
  if (runtimeInterfaces.length > 0) {
    return runtimeInterfaces.flatMap((iface) => {
      const interfaceName = iface.interface_name || '--';
      return selectedMetrics.map((field) => {
        const metric = iface.metrics?.[field];
        return {
          key: `${link.id}:${iface.endpoint ?? 'interface'}:${iface.bk_inst_id ?? interfaceName}:${field}`,
          interfaceName,
          metricLabel: labels[field] ?? field,
          value:
            metric && metric.value !== null && metric.value !== undefined
              ? formatNetworkMetricValue(metric.value, metric.unit)
              : '--',
        };
      });
    });
  }
  return link.port_pairs.flatMap((pair, index) =>
    ([
      ['source', pair.source_interface],
      ['target', pair.target_interface],
    ] as const).flatMap(([endpoint, ref]) =>
      selectedMetrics.map((field) => ({
        key: `${link.id}:${endpoint}:${ref.bk_inst_id || index}:${field}`,
        interfaceName: ref.interface_name || '--',
        metricLabel: labels[field] ?? field,
        value: '--',
      })),
    ),
  );
};

export const updateNetworkTopologyLinkTerminals = (
  links: ReadonlyArray<NetworkTopologyLink>,
  id: string,
  terminals: Pick<
    NetworkTopologyLink,
    'source_node_id' | 'target_node_id' | 'source_port_id' | 'target_port_id'
  >,
): NetworkTopologyLink[] =>
  links.map((link) =>
    link.id === id
      ? {
        ...link,
        source_node_id: terminals.source_node_id,
        target_node_id: terminals.target_node_id,
        source_port_id: terminals.source_port_id,
        target_port_id: terminals.target_port_id,
      }
      : link,
  );

export const isMetricOptionMatched = (
  input: string,
  option?: { label?: unknown; value?: unknown },
): boolean => {
  const keyword = input.trim().toLowerCase();
  if (!keyword) return true;
  return [option?.label, option?.value].some((item) =>
    String(item ?? '').toLowerCase().includes(keyword),
  );
};

/** 连线上的节点是否存在(以节点 ID 为单位)。 */
export const findNodeById = (
  nodes: ReadonlyArray<NetworkTopologyNode>,
  id: string,
): NetworkTopologyNode | undefined => nodes.find((node) => node.id === id);

/** 在删除节点时级联删除相关连线(source_node_id 或 target_node_id 命中)。 */
export const filterLinksByNode = (
  links: ReadonlyArray<NetworkTopologyLink>,
  nodeId: string,
): NetworkTopologyLink[] =>
  links.filter(
    (link) => link.source_node_id !== nodeId && link.target_node_id !== nodeId,
  );

/** 节点级 → 序号:返回最早未占用的 default 数值 ID(用于新增节点 / 连线)。 */
export const nextSequentialId = (
  prefix: string,
  existingIds: ReadonlyArray<string>,
): string => {
  let max = 0;
  for (const id of existingIds) {
    if (typeof id !== 'string') continue;
    if (!id.startsWith(`${prefix}-`)) continue;
    const tail = Number(id.slice(prefix.length + 1));
    if (Number.isFinite(tail) && tail > max) max = tail;
  }
  return `${prefix}-${max + 1}`;
};

/** 基于当前节点数自动给节点默认位置(避免重叠)。 */
export const defaultNodePosition = (
  count: number,
): { x: number; y: number } => ({
  x: 80 + (count % 8) * 220,
  y: 80 + Math.floor(count / 8) * 160,
});

/** 把 WeOps 接口状态归一化为字符串(空值 / 未知字符串 -> unknown)。 */
export const normalizeInterfaceStatus = (
  value: unknown,
): 'up' | 'down' | 'testing' | 'unknown' => {
  if (value === null || value === undefined) return 'unknown';
  if (typeof value !== 'string' && typeof value !== 'number') return 'unknown';
  if (value === 'up' || value === 'down' || value === 'testing') return value;
  if (value === 1 || value === '1') return 'up';
  if (value === 2 || value === '2') return 'down';
  if (value === 3 || value === '3') return 'testing';
  return 'unknown';
};
