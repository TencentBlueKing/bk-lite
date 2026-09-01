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
}

export const buildSearchQueryParams = ({
  group,
  metrics,
  instances,
  timeRange
}: BuildSearchQueryParamsArgs): SearchParams => {
  const metricItem = resolveMetricSelection(metrics, group.metric);
  const selectedInstances = instances.filter((item) =>
    group.instanceIds.includes(item.instance_id)
  );
  const params: SearchParams = {
    monitor_object_id: group.object,
    metric_id: metricItem?.id,
    instance_ids: selectedInstances.map((item) => item.instance_id),
    aggregation: group.aggregation || 'AVG',
    filters: group.conditions
      .filter(
        (condition) =>
          condition.label && condition.condition && condition.value
      )
      .map((condition) => ({
        label: String(condition.label),
        operator: String(condition.condition),
        value: condition.value
      })),
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
