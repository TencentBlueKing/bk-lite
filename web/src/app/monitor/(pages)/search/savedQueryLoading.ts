import type React from 'react';

import type { MetricItem } from '@/app/monitor/types';
import type {
  InstanceItem,
  PluginItem,
  QueryGroup
} from '@/app/monitor/types/search';

interface LoadSavedQueryResourcesArgs {
  queryGroups: QueryGroup[];
  pluginsMap: Record<string, PluginItem[]>;
  metricsMap: Record<string, MetricItem[]>;
  instancesMap: Record<string, InstanceItem[]>;
  loadPlugins: (objectId: React.Key) => Promise<PluginItem[]>;
  loadMetrics: (
    objectId: React.Key,
    pluginId: React.Key | null
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

      await Promise.all(
        groupsForObject.map(async (group) => {
          const pluginId = resolvePlugin(plugins, group);
          if (pluginId && !group.plugin) group.plugin = pluginId;
          const resourceKey = getResourceKey(objectId, pluginId);
          const metricsPromise = loadedMetricsMap[resourceKey]
            ? Promise.resolve(loadedMetricsMap[resourceKey])
            : getOrCreateRequest(metricRequests, resourceKey, () =>
              loadMetrics(objectId, pluginId)
            );
          const instancesPromise = loadedInstancesMap[resourceKey]
            ? Promise.resolve(loadedInstancesMap[resourceKey])
            : getOrCreateRequest(instanceRequests, resourceKey, () =>
              loadInstances(objectId, pluginId)
            );
          const [metrics, instances] = await Promise.all([
            metricsPromise,
            instancesPromise
          ]);

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
          loadedMetricsMap[resourceKey] = metrics;
          loadedInstancesMap[resourceKey] = instances;
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
