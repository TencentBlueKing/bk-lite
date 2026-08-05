import { unwrapMonitorPluginList } from './monitorPluginList';

type PluginRow = Record<string, any>;

/** 按监控对象缓存插件下拉(搜索/策略等),与集成列表分页路径隔离 */
const pluginCache = new Map<string, PluginRow[]>();
const inflight = new Map<string, Promise<PluginRow[]>>();

const cacheKey = (monitorObjectId: string | number | null | undefined) =>
  monitorObjectId == null || monitorObjectId === ''
    ? '__all__'
    : String(monitorObjectId);

export const invalidateMonitorPluginCache = (
  monitorObjectId?: string | number | null
) => {
  if (monitorObjectId === undefined) {
    pluginCache.clear();
    inflight.clear();
    return;
  }
  const key = cacheKey(monitorObjectId);
  pluginCache.delete(key);
  inflight.delete(key);
};

export const loadMonitorPluginsByObjectCached = async (
  monitorObjectId: string | number | null | undefined,
  fetcher: () => Promise<unknown>
): Promise<PluginRow[]> => {
  const key = cacheKey(monitorObjectId);
  const cached = pluginCache.get(key);
  if (cached) {
    return cached;
  }
  const pending = inflight.get(key);
  if (pending) {
    return pending;
  }
  const request = (async () => {
    const data = await fetcher();
    const list = unwrapMonitorPluginList<PluginRow>(data);
    pluginCache.set(key, list);
    return list;
  })();
  inflight.set(key, request);
  try {
    return await request;
  } finally {
    inflight.delete(key);
  }
};
