import type { AppWidgetKey } from '@/context/appCapabilities/widgets';

export interface CmdbPublicMenuItem {
  key:
    | 'monitorView'
    | 'alertList'
    | 'monitorPolicy'
    | 'nodeStatus'
    | 'networkStatusTopology'
    | 'application3D'
    | 'room3D';
  widgetKey: AppWidgetKey;
  titleKey: string;
  url: string;
}

const DETAIL_BASE = '/cmdb/assetData/detail';

// 这些侧栏项没有独立页面，点击落到关联关系页的对应 Segmented tab。
const RELATIONSHIP_TAB_BY_MENU_KEY: Partial<
  Record<CmdbPublicMenuItem['key'], string>
> = {
  networkStatusTopology: 'networkStatusTopology',
  room3D: 'room3D',
};

export function relationshipTabForPublicMenuKey(
  key: CmdbPublicMenuItem['key'],
): string {
  return RELATIONSHIP_TAB_BY_MENU_KEY[key] || '';
}

export function resolveCmdbPublicMenuItems(input: {
  instUuid: string;
  modelId: string;
  monitorId: string;
  nodeId: string;
  isNetworkDevice: boolean;
  widgets: Partial<Record<AppWidgetKey, boolean>>;
}): CmdbPublicMenuItem[] {
  const instUuid = input.instUuid.trim();
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
  if (!instUuid) {
    return items;
  }
  if (input.isNetworkDevice && canShow('ops-analysis.networkStatusTopology')) {
    items.push({
      key: 'networkStatusTopology',
      widgetKey: 'ops-analysis.networkStatusTopology',
      titleKey: 'Model.publicNetworkStatusTopology',
      url: `${DETAIL_BASE}/networkStatusTopology`,
    });
  }
  if (input.modelId === 'system' && canShow('ops-analysis.application3D')) {
    items.push({
      key: 'application3D',
      widgetKey: 'ops-analysis.application3D',
      titleKey: 'Model.publicApplication3D',
      url: `${DETAIL_BASE}/application3D`,
    });
  }
  if (input.modelId === 'server_room' && canShow('ops-analysis.room3D')) {
    items.push({
      key: 'room3D',
      widgetKey: 'ops-analysis.room3D',
      titleKey: 'Model.publicRoom3D',
      url: `${DETAIL_BASE}/room3D`,
    });
  }
  return items;
}
