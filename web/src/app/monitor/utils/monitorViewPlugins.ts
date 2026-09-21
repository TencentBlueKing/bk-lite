import type { Key } from 'react';
import type { ViewPluginOption } from '@/app/monitor/types/view';

export interface MonitorViewPluginSource {
  id?: Key | null;
  name?: string | null;
  display_name?: string | null;
  is_pre?: boolean;
  is_custom?: boolean;
}

export interface FormatMonitorViewPluginTabsOptions {
  /**
   * 当前监控对象的展示名。云厂商共用插件（如 Aliyun Cloud→「阿里云」）时，
   * 单插件详情 Tab 应显示对象名（如「云数据库 Redis」），避免看起来像查错了对象。
   */
  objectDisplayName?: string | null;
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
 *
 * 仅一个有效插件且传入 objectDisplayName 时，用对象展示名作为 Tab 文案；
 * 多插件（如 Host + 进程）仍用各插件自己的 display_name，避免互相覆盖。
 */
export function formatMonitorViewPluginTabs(
  items: MonitorViewPluginSource[] | null | undefined,
  options?: FormatMonitorViewPluginTabsOptions,
): ViewPluginOption[] {
  const objectLabel = String(options?.objectDisplayName || '').trim();
  const sorted = (items || [])
    .filter(hasPluginId)
    .slice()
    .sort((left, right) => pluginTabOrder(left) - pluginTabOrder(right));
  const preferObjectLabel = Boolean(objectLabel) && sorted.length === 1;
  return sorted.map((item) => ({
    label: preferObjectLabel
      ? objectLabel
      : String(item.display_name || item.name || '--'),
    value: String(item.id),
  }));
}
