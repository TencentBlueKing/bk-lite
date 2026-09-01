import type { FlowDashboardPlugin } from './flow-dashboard-route';

const cache = new Map<string, FlowDashboardPlugin[]>();

export const flowPluginCacheKey = (monitorObjectId: string, instanceId: string) =>
  `${monitorObjectId}:${instanceId}`;

export const getCachedFlowPlugins = (key: string): FlowDashboardPlugin[] | undefined =>
  cache.get(key);

export const setCachedFlowPlugins = (key: string, plugins: FlowDashboardPlugin[]) => {
  cache.set(key, plugins);
};
