import type React from 'react';

import type { TimeValuesProps, MetricItem } from '@/app/monitor/types';
import type {
  InstanceItem,
  PluginItem,
  QueryGroup,
  SearchParams
} from '@/app/monitor/types/search';
import { getRecentTimeRange } from '@/app/monitor/utils/common';
import { buildGapDetectionParams } from '@/app/monitor/utils/gapIntervals';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';

interface SearchIdCrypto {
  randomUUID?: () => string;
  getRandomValues?: (values: Uint8Array) => Uint8Array;
}

export const generateSearchId = (
  cryptoApi: SearchIdCrypto | undefined = globalThis.crypto
) => {
  if (typeof cryptoApi?.randomUUID === 'function') {
    return cryptoApi.randomUUID();
  }

  const values = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === 'function') {
    cryptoApi.getRandomValues(values);
  } else {
    values.forEach((_, index) => {
      values[index] = Math.floor(Math.random() * 256);
    });
  }
  values[6] = (values[6] & 0x0f) | 0x40;
  values[8] = (values[8] & 0x3f) | 0x80;
  const hex = Array.from(values, (value) =>
    value.toString(16).padStart(2, '0')
  ).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

export const getMetricsMapKey = (
  objectId: React.Key,
  pluginId?: React.Key | null
) =>
  pluginId !== null && pluginId !== undefined && pluginId !== ''
    ? `${String(objectId)}_${String(pluginId)}`
    : String(objectId);

export const normalizeMonitorEntityId = (
  value: unknown
): React.Key | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  if (!normalized) return null;
  return /^\d+$/.test(normalized) ? Number(normalized) : normalized;
};

export const resolveInitialPlugin = (plugins: PluginItem[]): React.Key | null =>
  plugins.length === 1 ? plugins[0].id : null;

/** 单选历史值和多选数组都收成去重后的指标 ID。空值得到空数组。 */
export const listSelectedMetricIds = (metric: unknown): React.Key[] => {
  const values = Array.isArray(metric) ? metric : [metric];
  const ids: React.Key[] = [];
  for (const value of values) {
    if (value === null || value === undefined || value === '') continue;
    const normalized = normalizeMonitorEntityId(value);
    if (normalized === null) continue;
    if (ids.some((id) => String(id) === String(normalized))) continue;
    ids.push(normalized);
  }
  return ids;
};

/** 读已保存条件：数字 ID（单个或数组）变成多选；非数字字符串仍是旧指标名。 */
export const readSavedMetricSelection = (
  metric: unknown,
  legacyName?: string | null
): { metric: React.Key[]; legacyMetricName: string | null } => {
  if (typeof metric === 'string' && metric.trim() && !/^\d+$/.test(metric.trim())) {
    return {
      metric: [],
      legacyMetricName: legacyName || metric.trim()
    };
  }
  return {
    metric: listSelectedMetricIds(metric),
    legacyMetricName: legacyName || null
  };
};

/** 保存时始终写成 ID 数组，旧的单个 ID 在加载时再兼容。 */
export const writeSavedMetricIds = (metric: unknown): React.Key[] | null => {
  const ids = listSelectedMetricIds(metric);
  return ids.length ? ids : null;
};

export const isSameMetricIdentity = (
  metric: MetricItem,
  selectedMetric: React.Key | null | undefined
) => {
  if (selectedMetric === null || selectedMetric === undefined) return false;
  return String(metric.id) === String(selectedMetric);
};

export const resolveMetricSelection = (
  metrics: MetricItem[],
  selectedMetric: React.Key | null | undefined
) => {
  if (selectedMetric === null || selectedMetric === undefined) return null;
  const byId = metrics.find((item) =>
    isSameMetricIdentity(item, selectedMetric)
  );
  if (byId) return byId;
  return metrics.find((item) => item.name === String(selectedMetric)) || null;
};

/** 从指标定义解析条件「标签」可选维度名，兼容 [{name}] / ["name"]。 */
export const resolveMetricDimensionLabels = (
  metric: MetricItem | null | undefined
): string[] => {
  const dimensions = metric?.dimensions as unknown;
  if (!Array.isArray(dimensions) || !dimensions.length) return [];
  return dimensions
    .map((item) => {
      if (typeof item === 'string') return item.trim();
      if (item && typeof item === 'object' && 'name' in item) {
        return String((item as { name?: unknown }).name || '').trim();
      }
      return '';
    })
    .filter(Boolean);
};

/** 多指标共用的筛选标签：只保留每个已选指标都声明了的维度。 */
export const intersectMetricDimensionLabels = (
  metrics: Array<MetricItem | null | undefined>
): string[] => {
  const lists = metrics
    .filter((metric): metric is MetricItem => Boolean(metric))
    .map((metric) => resolveMetricDimensionLabels(metric));
  if (!lists.length) return [];
  const [first, ...rest] = lists;
  return first.filter((label) => rest.every((list) => list.includes(label)));
};

export interface SearchMetricCard {
  cardId: string;
  group: QueryGroup;
  metricId: React.Key;
}

/** 一组查询里选了几个指标，就拆成几张结果卡，每张卡对应一次单指标查询。 */
export const expandSearchCards = (groups: QueryGroup[]): SearchMetricCard[] => {
  const cards: SearchMetricCard[] = [];
  for (const group of groups) {
    if (!group.instanceIds.length) continue;
    for (const metricId of listSelectedMetricIds(group.metric)) {
      cards.push({
        cardId: `${group.id}:${String(metricId)}`,
        group,
        metricId
      });
    }
  }
  return cards;
};

/** 从 query_by_instance 结果中提取指定维度标签的可选值。 */
export const extractDimensionLabelValues = (
  series: Array<{ metric?: Record<string, string> }> | null | undefined,
  label: string | null | undefined
): string[] => {
  const key = String(label || '').trim();
  if (!key || !Array.isArray(series) || !series.length) return [];
  const values = new Set<string>();
  for (const item of series) {
    const raw = item?.metric?.[key];
    if (raw === null || raw === undefined) continue;
    const text = String(raw).trim();
    if (text) values.add(text);
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b));
};

interface BuildSearchQueryParamsArgs {
  group: QueryGroup;
  metrics: MetricItem[];
  instances: InstanceItem[];
  timeRange: TimeValuesProps;
  metricId?: React.Key | null;
}

export const buildSearchQueryParams = ({
  group,
  metrics,
  instances,
  timeRange,
  metricId
}: BuildSearchQueryParamsArgs): SearchParams => {
  const selectedIds = listSelectedMetricIds(group.metric);
  const metricItem = resolveMetricSelection(
    metrics,
    metricId ?? selectedIds[0] ?? null
  );
  const selectedInstances = instances.filter((item) =>
    group.instanceIds.includes(item.instance_id)
  );
  const filters = group.conditions
    .filter(
      (condition) =>
        condition.label && condition.condition && condition.value
    )
    .map((condition) => ({
      label: String(condition.label),
      operator: String(condition.condition),
      value: condition.value
    }));
  const declaredLabels = new Set(resolveMetricDimensionLabels(metricItem));
  const params: SearchParams = {
    monitor_object_id: group.object,
    metric_id: metricItem?.id,
    instance_ids: selectedInstances.map((item) => item.instance_id),
    aggregation: group.aggregation || 'AVG',
    filters:
      selectedIds.length > 1
        ? filters.filter((item) => declaredLabels.has(item.label))
        : filters,
    source_unit: metricItem?.unit || ''
  };
  const recentTimeRange = getRecentTimeRange(timeRange);
  const startTime = recentTimeRange.at(0);
  const endTime = recentTimeRange.at(1);
  const collectionInterval = Math.max(0, ...selectedInstances.map((item) => Number(item.interval) || 0));
  if (Number.isFinite(startTime) && Number.isFinite(endTime)) {
    params.start = startTime;
    params.end = endTime;
    params.step = calculateQueryStep(
      params.start,
      params.end,
      collectionInterval
    );
  }
  return buildGapDetectionParams(params, collectionInterval);
};
