import type React from 'react';

import type { TimeValuesProps, MetricItem } from '@/app/monitor/types';
import type {
  InstanceItem,
  PluginItem,
  QueryGroup,
  SearchParams
} from '@/app/monitor/types/search';
import {
  getRecentTimeRange,
  mergeViewQueryKeyValues
} from '@/app/monitor/utils/common';
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
    ? `${objectId}_${pluginId}`
    : String(objectId);

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
  const queryValues: string[][] = selectedInstances.map(
    (item) => item.instance_id_values
  );
  const querykeys: string[] = metricItem?.instance_id_keys || [];
  const queryList = queryValues.map((values) => ({
    keys: querykeys,
    values
  }));
  const params: SearchParams = {
    query: '',
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
  let query = '';
  if (group.instanceIds.length) {
    query += mergeViewQueryKeyValues(queryList);
  }
  if (group.conditions.length) {
    const conditionQueries = group.conditions
      .map((condition) => {
        if (condition.label && condition.condition && condition.value) {
          return `${condition.label}${condition.condition}"${condition.value}"`;
        }
        return '';
      })
      .filter(Boolean);
    if (conditionQueries.length) {
      if (query) query += ',';
      query += conditionQueries.join(',');
    }
  }
  let finalQuery = (metricItem?.query || '').replace(/__\$labels__/g, query);
  if (group.aggregation && group.aggregation !== 'AVG') {
    const aggFunc = group.aggregation.toLowerCase();
    const byClause = querykeys.length ? ` by (${querykeys.join(',')})` : '';
    finalQuery = `${aggFunc}(${finalQuery})${byClause}`;
  }
  params.query = finalQuery;
  return buildGapDetectionParams(params, collectionInterval);
};
