import type { Key } from 'react';
import type { ViewPluginOption } from '@/app/monitor/types/view';

export interface MonitorViewPluginSource {
  id?: Key | null;
  name?: string | null;
  display_name?: string | null;
  is_pre?: boolean;
  is_custom?: boolean;
}

const pluginTabOrder = (item: MonitorViewPluginSource) =>
  item.is_pre ? 0 : !item.is_custom ? 1 : 2;

const hasPluginId = (item: MonitorViewPluginSource) => {
  if (item.id == null || item.id === '') {
    return false;
  }
  return String(item.id) !== 'undefined';
};

/**
 * MonitorView / 指标详情把 tab.value 当作 /api/metrics 的 monitor_plugin_id。
 * 必须用插件数字 ID，不能用 name（如 Host），否则目录接口 400。
 */
export function formatMonitorViewPluginTabs(
  items: MonitorViewPluginSource[] | null | undefined,
): ViewPluginOption[] {
  return (items || [])
    .filter(hasPluginId)
    .slice()
    .sort((left, right) => pluginTabOrder(left) - pluginTabOrder(right))
    .map((item) => ({
      label: String(item.display_name || item.name || '--'),
      value: String(item.id),
    }));
}
