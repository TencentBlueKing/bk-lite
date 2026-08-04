import { resolveProcessObjectId } from '@/app/monitor/dashboards/objects/host/host-metrics-process-object';

/** 主机监控视图里「进程」伪插件页签，与真实 plugin id 区分。 */
export const HOST_PROCESS_METRICS_TAB = '__host_process_metrics__';

export function isHostMonitorObject(name?: string | null): boolean {
  return String(name || '').toLowerCase() === 'host';
}

export function isHostProcessMetricsTab(tab: string | number | null | undefined): boolean {
  return String(tab || '') === HOST_PROCESS_METRICS_TAB;
}

export type HostProcessMetricsTarget = {
  processObjectId: string;
  processPluginId: string;
  /** 与 Process 对象页签一致，如「进程 (Telegraf)」 */
  processPluginLabel: string;
};

/**
 * 解析 Process 对象及其首个插件，供主机视图追加与 Process 页一致的插件页签。
 */
export async function resolveHostProcessMetricsTarget(api: {
  getMonitorObject: (params: {
    name?: string;
    include_invisible?: boolean;
  }) => Promise<unknown>;
  getMonitorPlugin: (params: {
    monitor_object_id?: string | number | null;
  }) => Promise<unknown>;
}): Promise<HostProcessMetricsTarget | null> {
  try {
    const objects = await api.getMonitorObject({
      name: 'Process',
      include_invisible: true
    });
    const processObjectId = resolveProcessObjectId(objects);
    if (!processObjectId) return null;

    const pluginResp = await api.getMonitorPlugin({
      monitor_object_id: processObjectId
    });
    const list = Array.isArray(pluginResp)
      ? pluginResp
      : (pluginResp as { items?: unknown[]; results?: unknown[] })?.items ||
        (pluginResp as { results?: unknown[] })?.results ||
        [];
    const first = (
      list as Array<{
        id?: string | number;
        display_name?: string;
        name?: string;
      }>
    ).find((item) => item?.id != null);
    if (!first?.id) return null;

    return {
      processObjectId,
      processPluginId: String(first.id),
      processPluginLabel: String(first.display_name || first.name || '进程 (Telegraf)')
    };
  } catch {
    return null;
  }
}

export function withHostProcessMetricsTab<T extends { label: string; value: string }>(
  plugins: T[],
  enabled: boolean,
  label = '进程 (Telegraf)'
): T[] {
  if (!enabled) return plugins;
  if (plugins.some((item) => String(item.value) === HOST_PROCESS_METRICS_TAB)) {
    return plugins;
  }
  return [
    ...plugins,
    { label, value: HOST_PROCESS_METRICS_TAB } as T
  ];
}

/** 从进程实例行取出 process_name（优先 identity 第二段）。 */
export function resolveProcessNameFromInstance(item: {
  instance_id_values?: unknown;
  instance_name?: unknown;
}): string {
  const values = Array.isArray(item.instance_id_values)
    ? item.instance_id_values.map((v) => String(v ?? ''))
    : [];
  const fromIdentity = String(values[1] || '').trim();
  if (fromIdentity) return fromIdentity;
  return String(item.instance_name || '').trim();
}

/**
 * 主机下钻进程页的 PromQL 标签对。
 * 未选进程时仅按主机 instance_id 过滤（展示该主机全部进程）；
 * 选中后叠加 process_name，避免图上序列过多难以定位。
 */
export function buildHostProcessLabelPairs(
  hostId: string,
  processNames: readonly string[]
): Array<{ keys: string[]; values: string[] }> {
  const host = String(hostId || '').trim();
  if (!host) return [];
  const names = processNames.map((name) => String(name || '').trim()).filter(Boolean);
  if (!names.length) {
    return [{ keys: ['instance_id'], values: [host] }];
  }
  return names.map((name) => ({
    keys: ['instance_id', 'process_name'],
    values: [host, name]
  }));
}
