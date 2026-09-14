import type React from 'react';

import type { MetricItem } from '@/app/monitor/types';
import type {
  InstanceItem,
  PluginItem,
  QueryGroup
} from '@/app/monitor/types/search';
import {
  collectMetricIdsByResource,
  mergeMetricsById
} from './savedQueryMetricMerge';

interface LoadSavedQueryResourcesArgs {
  queryGroups: QueryGroup[];
  pluginsMap: Record<string, PluginItem[]>;
  metricsMap: Record<string, MetricItem[]>;
  instancesMap: Record<string, InstanceItem[]>;
  loadPlugins: (objectId: React.Key) => Promise<PluginItem[]>;
  loadMetrics: (
    objectId: React.Key,
    pluginId: React.Key | null,
    selectedMetricId?: React.Key | null
  ) => Promise<MetricItem[]>;
  loadInstances: (
    objectId: React.Key,
    pluginId: React.Key | null
  ) => Promise<InstanceItem[]>;
  getResourceKey: (
    objectId: React.Key,
    pluginId: React.Key | null
  ) => string;
  resolvePlugin: (
    plugins: PluginItem[],
    group: QueryGroup
  ) => React.Key | null;
  resolveLegacyMetric: (
    metrics: MetricItem[],
    legacyName: string
  ) => MetricItem | null;
}

interface LoadSavedQueryResourcesResult {
  queryGroups: QueryGroup[];
  pluginsMap: Record<string, PluginItem[]>;
  metricsMap: Record<string, MetricItem[]>;
  instancesMap: Record<string, InstanceItem[]>;
}

const getOrCreateRequest = <T>(
  requests: Map<string, Promise<T>>,
  key: string,
  load: () => Promise<T>
) => {
  const inFlight = requests.get(key);
  if (inFlight) return inFlight;
  const request = load().finally(() => requests.delete(key));
  requests.set(key, request);
  return request;
};

export const loadSavedQueryResources = async ({
  queryGroups,
  pluginsMap,
  metricsMap,
  instancesMap,
  loadPlugins,
  loadMetrics,
  loadInstances,
  getResourceKey,
  resolvePlugin,
  resolveLegacyMetric
}: LoadSavedQueryResourcesArgs): Promise<LoadSavedQueryResourcesResult> => {
  const loadedPluginsMap = { ...pluginsMap };
  const loadedMetricsMap = { ...metricsMap };
  const loadedInstancesMap = { ...instancesMap };
  const metricRequests = new Map<string, Promise<MetricItem[]>>();
  const instanceRequests = new Map<string, Promise<InstanceItem[]>>();
  const objectIds = [
    ...new Set(queryGroups.map((group) => group.object).filter(Boolean))
  ];

  await Promise.all(
    objectIds.map(async (objectId) => {
      const objectKey = String(objectId);
      const plugins =
        loadedPluginsMap[objectKey] || (await loadPlugins(objectId));
      loadedPluginsMap[objectKey] = plugins;
      const groupsForObject = queryGroups.filter(
        (group) => group.object === objectId
      );

      for (const group of groupsForObject) {
        const pluginId = resolvePlugin(plugins, group);
        if (pluginId && !group.plugin) group.plugin = pluginId;
      }

      const resourceIds = collectMetricIdsByResource(
        groupsForObject,
        getResourceKey
      );

      await Promise.all(
        [...resourceIds.entries()].map(async ([resourceKey, resource]) => {
          const { pluginId, metricIds } = resource;
          const groupsForResource = groupsForObject.filter(
            (group) => getResourceKey(objectId, group.plugin) === resourceKey
          );
          const instancesPromise = loadedInstancesMap[resourceKey]
            ? Promise.resolve(loadedInstancesMap[resourceKey])
            : getOrCreateRequest(instanceRequests, resourceKey, () =>
              loadInstances(objectId, pluginId)
            );

          const cached = loadedMetricsMap[resourceKey] || [];
          const missingFromCache = metricIds.filter(
            (id) => !cached.some((metric) => String(metric.id) === String(id))
          );
          let metrics = cached;
          if (!cached.length || missingFromCache.length) {
            const catalog = cached.length
              ? cached
              : await getOrCreateRequest(
                metricRequests,
                `${resourceKey}|catalog`,
                () => loadMetrics(objectId, pluginId)
              );
            metrics = mergeMetricsById(metrics, catalog);
            const stillMissing = metricIds.filter(
              (id) =>
                !metrics.some((metric) => String(metric.id) === String(id))
            );
            const extras = await Promise.all(
              stillMissing.map((id) =>
                getOrCreateRequest(
                  metricRequests,
                  `${resourceKey}|${String(id)}`,
                  () => loadMetrics(objectId, pluginId, id)
                )
              )
            );
            for (const extra of extras) {
              metrics = mergeMetricsById(metrics, extra);
            }
          }

          loadedMetricsMap[resourceKey] = metrics;
          loadedInstancesMap[resourceKey] = await instancesPromise;

          for (const group of groupsForResource) {
            if (group.legacyMetricName && !group.metric) {
              const legacyMetric = resolveLegacyMetric(
                metrics,
                group.legacyMetricName
              );
              if (legacyMetric) {
                group.metric = legacyMetric.id;
                group.legacyMetricName = null;
              }
            }
          }
        })
      );
    })
  );

  return {
    queryGroups,
    pluginsMap: loadedPluginsMap,
    metricsMap: loadedMetricsMap,
    instancesMap: loadedInstancesMap
  };
};
