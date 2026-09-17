import type { AppWidgetKey } from '@/context/appCapabilities/widgets';

export interface CmdbPublicMenuItem {
  key: 'monitorView' | 'alertList' | 'monitorPolicy' | 'nodeStatus';
  widgetKey: AppWidgetKey;
  titleKey: string;
  url: string;
}

const DETAIL_BASE = '/cmdb/assetData/detail';

export function resolveCmdbPublicMenuItems(input: {
  modelId: string;
  monitorId: string;
  nodeId: string;
  widgets: Partial<Record<AppWidgetKey, boolean>>;
}): CmdbPublicMenuItem[] {
  const monitorId = input.monitorId.trim();
  const nodeId = input.nodeId.trim();
  const items: CmdbPublicMenuItem[] = [];
  // 提供方未购 / 无模块级访问时目录探测不到该键，declared 即为 false。
  const canShow = (widgetKey: AppWidgetKey) => Boolean(input.widgets[widgetKey]);

  if (monitorId && canShow('monitor.monitorView')) {
    items.push({
      key: 'monitorView',
      widgetKey: 'monitor.monitorView',
      titleKey: 'Model.publicMonitorView',
      url: `${DETAIL_BASE}/monitorView`,
    });
  }
  if (monitorId && canShow('monitor.alertList')) {
    items.push({
      key: 'alertList',
      widgetKey: 'monitor.alertList',
      titleKey: 'Model.publicAlertList',
      url: `${DETAIL_BASE}/alertList`,
    });
  }
  if (monitorId && canShow('monitor.monitorPolicy')) {
    items.push({
      key: 'monitorPolicy',
      widgetKey: 'monitor.monitorPolicy',
      titleKey: 'Model.publicMonitorPolicy',
      url: `${DETAIL_BASE}/monitorPolicy`,
    });
  }
  if (input.modelId === 'host' && nodeId && canShow('node.nodeStatus')) {
    items.push({
      key: 'nodeStatus',
      widgetKey: 'node.nodeStatus',
      titleKey: 'Model.publicNodeStatus',
      url: `${DETAIL_BASE}/nodeStatus`,
    });
  }
  return items;
}
