import type React from 'react';

import type { MetricItem } from '@/app/monitor/types';

export interface ResourceMetricIds {
  objectId: React.Key;
  pluginId: React.Key | null;
  metricIds: React.Key[];
}

export const collectMetricIdsByResource = (
  groups: Array<{
    object: React.Key;
    plugin?: React.Key | null;
    metric?: React.Key | null;
  }>,
  getResourceKey: (objectId: React.Key, pluginId: React.Key | null) => string
): Map<string, ResourceMetricIds> => {
  const collected = new Map<string, ResourceMetricIds>();
  for (const group of groups) {
    const pluginId = group.plugin ?? null;
    const resourceKey = getResourceKey(group.object, pluginId);
    const current = collected.get(resourceKey) || {
      objectId: group.object,
      pluginId,
      metricIds: []
    };
    if (
      group.metric !== null &&
      group.metric !== undefined &&
      group.metric !== '' &&
      !current.metricIds.some((id) => String(id) === String(group.metric))
    ) {
      current.metricIds.push(group.metric);
    }
    collected.set(resourceKey, current);
  }
  return collected;
};

export const mergeMetricsById = (
  existing: MetricItem[] = [],
  incoming: MetricItem[] = []
): MetricItem[] => {
  const byId = new Map<string, MetricItem>();
  for (const metric of existing) {
    if (metric?.id === undefined || metric.id === null) continue;
    byId.set(String(metric.id), metric);
  }
  for (const metric of incoming) {
    if (metric?.id === undefined || metric.id === null) continue;
    byId.set(String(metric.id), metric);
  }
  return Array.from(byId.values());
};

export const writeMetricsMap = (
  map: Record<string, MetricItem[]>,
  resourceKey: string,
  incoming: MetricItem[]
): Record<string, MetricItem[]> => {
  if (!incoming.length) {
    return map;
  }
  return {
    ...map,
    [resourceKey]: mergeMetricsById(map[resourceKey], incoming)
  };
};

export const getMetricsAbortKey = (
  resourceKey: string,
  keyword = '',
  groupId?: string,
  selectedMetricId?: React.Key | null
): string => {
  if (keyword.trim() && groupId) {
    return `${resourceKey}|${groupId}`;
  }
  if (
    selectedMetricId !== null &&
    selectedMetricId !== undefined &&
    selectedMetricId !== ''
  ) {
    return `${resourceKey}|metric:${String(selectedMetricId)}`;
  }
  return resourceKey;
};
